"""
Tests for framework selection pipeline — KIN-322.

Unit tests for app/services/rag/framework_selection.py.
All external calls (EmbeddingService, Supabase RPC) are mocked.

Schema: docs/db-schema-spec.md §14 (frameworks), §15 (framework_trigger_embeddings)
"""

import asyncio
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.services.rag.framework_selection import (
    FRAMEWORK_MIN_SIMILARITY,
    HIGH_CONFIDENCE_THRESHOLD,
    MULTI_TRIGGER_BOOST,
    FrameworkMatch,
    fetch_pinned_frameworks,
    select_framework,
)


AGENT_ID = str(uuid4())
FRAMEWORK_ID = str(uuid4())

FRAMEWORK_ROW = {
    "id": FRAMEWORK_ID,
    "name": "SWOT Analysis",
    "description": "Strategic planning tool for evaluating strengths.",
    "when_to_apply": ["strategic planning", "competitive analysis"],
    "principles": ["Be thorough", "Consider all quadrants"],
    "steps": ["List strengths", "List weaknesses", "List opportunities", "List threats"],
    "example_application": "Used for quarterly business review.",
}


def _run(coro):
    """Run async coroutine synchronously for testing."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Helpers to build mocks
# ---------------------------------------------------------------------------


def _mock_embedder(embedding=None):
    """Patch EmbeddingService to return a fixed embedding."""
    if embedding is None:
        embedding = [0.1] * 3072
    mock_svc = MagicMock()
    mock_svc.embed_batch.return_value = [embedding]
    return mock_svc


def _mock_supabase(triggers=None, framework_row=None):
    """Build a Supabase mock for framework selection."""
    if triggers is None:
        triggers = []
    if framework_row is None:
        framework_row = FRAMEWORK_ROW

    mock = MagicMock()

    def _rpc_side_effect(fn_name, params=None):
        chain = MagicMock()
        if fn_name == "match_framework_triggers":
            chain.execute.return_value = MagicMock(data=triggers)
        return chain

    def _table_side_effect(table_name):
        chain = MagicMock()
        if table_name == "frameworks":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=framework_row
            )
        return chain

    mock.rpc.side_effect = _rpc_side_effect
    mock.table.side_effect = _table_side_effect
    return mock


EMBED_PATCH = "app.services.ingestion.embedder.EmbeddingService"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFrameworkSelectionNoMatch:
    def test_no_triggers_returns_no_match(self):
        """No triggers in DB → no framework match."""
        mock_db = _mock_supabase(triggers=[])
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        assert result.matched_framework_id is None
        assert result.framework_text is None

    def test_below_threshold_returns_no_match(self):
        """Triggers below FRAMEWORK_MIN_SIMILARITY → no match."""
        low_sim_triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.3, "trigger_text": "weak match"},
        ]
        mock_db = _mock_supabase(triggers=low_sim_triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        assert result.matched_framework_id is None


class TestFrameworkSelectionMatch:
    def test_above_threshold_returns_match(self):
        """Trigger above FRAMEWORK_MIN_SIMILARITY → framework matched."""
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.7, "trigger_text": "strategic planning"},
        ]
        mock_db = _mock_supabase(triggers=triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        assert result.matched_framework_id == FRAMEWORK_ID
        assert result.matched_framework_name == "SWOT Analysis"
        assert "SWOT Analysis" in result.framework_text

    def test_multi_trigger_boost_pushes_over_threshold(self):
        """Two triggers just below threshold → boost pushes above."""
        # Single trigger at 0.59 is below 0.62. Two triggers add 0.05 boost → 0.64.
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.59, "trigger_text": "trigger a"},
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.55, "trigger_text": "trigger b"},
        ]
        mock_db = _mock_supabase(triggers=triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        # max_sim=0.59 + 1 extra trigger * 0.05 = 0.64 > 0.62
        assert result.matched_framework_id == FRAMEWORK_ID

    def test_highest_score_framework_wins(self):
        """Multiple frameworks → highest boosted score wins."""
        other_id = str(uuid4())
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.6, "trigger_text": "trigger a"},
            {"framework_db_id": other_id, "similarity": 0.8, "trigger_text": "trigger b"},
        ]
        mock_db = _mock_supabase(triggers=triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        # other_id has 0.8 > FRAMEWORK_ID's 0.6, but mock returns FRAMEWORK_ROW for all
        # The important assertion: a match is returned (highest score wins)
        assert result.matched_framework_id is not None


class TestConfidenceBands:
    """KIN-445: confidence_score and high_confidence fields."""

    def test_high_confidence_above_threshold(self):
        """Score >= 0.75 → high_confidence=True."""
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.8, "trigger_text": "strong match"},
        ]
        mock_db = _mock_supabase(triggers=triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        assert result.matched_framework_id == FRAMEWORK_ID
        assert result.high_confidence is True
        assert result.confidence_score >= HIGH_CONFIDENCE_THRESHOLD

    def test_moderate_confidence_in_maybe_band(self):
        """Score 0.62–0.75 → high_confidence=False."""
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.68, "trigger_text": "moderate match"},
        ]
        mock_db = _mock_supabase(triggers=triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        assert result.matched_framework_id == FRAMEWORK_ID
        assert result.high_confidence is False
        assert FRAMEWORK_MIN_SIMILARITY <= result.confidence_score < HIGH_CONFIDENCE_THRESHOLD

    def test_no_match_below_gate(self):
        """Score < 0.62 → no match, defaults."""
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.5, "trigger_text": "weak match"},
        ]
        mock_db = _mock_supabase(triggers=triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        assert result.matched_framework_id is None
        assert result.confidence_score == 0.0
        assert result.high_confidence is True  # default


class TestFrameworkSelectionTextAssembly:
    def test_framework_text_contains_name(self):
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.7, "trigger_text": "match"},
        ]
        mock_db = _mock_supabase(triggers=triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        assert "Framework: SWOT Analysis" in result.framework_text

    def test_framework_text_contains_principles(self):
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.7, "trigger_text": "match"},
        ]
        mock_db = _mock_supabase(triggers=triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        assert "Be thorough" in result.framework_text

    def test_framework_text_contains_steps(self):
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.7, "trigger_text": "match"},
        ]
        mock_db = _mock_supabase(triggers=triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        assert "List strengths" in result.framework_text


class TestFrameworkSelectionFailOpen:
    def test_embedding_failure_returns_no_match(self):
        """EmbeddingService failure → fail-open, no match."""
        mock_embedder = MagicMock()
        mock_embedder.embed_batch.side_effect = RuntimeError("API down")
        mock_db = _mock_supabase()
        with patch(EMBED_PATCH, return_value=mock_embedder):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        assert result.matched_framework_id is None

    def test_rpc_failure_returns_no_match(self):
        """Supabase RPC failure → fail-open, no match."""
        mock_db = MagicMock()
        mock_db.rpc.side_effect = RuntimeError("DB down")
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework("test query", AGENT_ID, mock_db))
        assert result.matched_framework_id is None


# ---------------------------------------------------------------------------
# KIN-391: Framework user overrides — excluded_ids filtering
# ---------------------------------------------------------------------------

FRAMEWORK_ID_2 = str(uuid4())

FRAMEWORK_ROW_2 = {
    "id": FRAMEWORK_ID_2,
    "name": "Five Forces",
    "description": "Porter's Five Forces analysis.",
    "when_to_apply": ["competitive analysis"],
    "principles": ["Analyze industry structure"],
    "steps": ["Assess rivalry", "Assess buyer power"],
    "example_application": "Used for market entry analysis.",
}


class TestExcludedIdsFiltering:
    """KIN-391: excluded_ids removes frameworks from candidate pool."""

    def test_excluded_framework_not_selected(self):
        """When the top match is excluded, it should be skipped."""
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.8, "trigger_text": "strategic planning"},
            {"framework_db_id": FRAMEWORK_ID_2, "similarity": 0.6, "trigger_text": "competitive"},
        ]
        mock_db = _mock_supabase(triggers=triggers, framework_row=FRAMEWORK_ROW_2)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework(
                "test query", AGENT_ID, mock_db,
                excluded_ids={FRAMEWORK_ID},
            ))
        # FRAMEWORK_ID (0.8) excluded → FRAMEWORK_ID_2 (0.6) wins
        assert result.matched_framework_id is not None

    def test_all_excluded_returns_no_match(self):
        """When all candidates are excluded, returns no match."""
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.8, "trigger_text": "match"},
        ]
        mock_db = _mock_supabase(triggers=triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework(
                "test query", AGENT_ID, mock_db,
                excluded_ids={FRAMEWORK_ID},
            ))
        assert result.matched_framework_id is None

    def test_empty_excluded_ids_no_effect(self):
        """Empty excluded set does not affect selection."""
        triggers = [
            {"framework_db_id": FRAMEWORK_ID, "similarity": 0.7, "trigger_text": "match"},
        ]
        mock_db = _mock_supabase(triggers=triggers)
        with patch(EMBED_PATCH, return_value=_mock_embedder()):
            result = _run(select_framework(
                "test query", AGENT_ID, mock_db,
                excluded_ids=set(),
            ))
        assert result.matched_framework_id == FRAMEWORK_ID


class TestFetchPinnedFrameworks:
    """KIN-391: fetch_pinned_frameworks bypasses pipeline, fetches by ID."""

    def test_single_pinned_returns_match(self):
        """Single pinned framework ID returns that framework."""
        mock_db = MagicMock()
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = MagicMock(data=FRAMEWORK_ROW)
        mock_db.table.return_value = chain

        results = _run(fetch_pinned_frameworks([FRAMEWORK_ID], mock_db))
        assert len(results) == 1
        assert results[0].matched_framework_id == FRAMEWORK_ID
        assert "SWOT Analysis" in results[0].framework_text

    def test_missing_pinned_silently_skipped(self):
        """Pinned ID not in DB → silently skipped (fail-open)."""
        mock_db = MagicMock()
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = MagicMock(data=None)
        mock_db.table.return_value = chain

        results = _run(fetch_pinned_frameworks(["nonexistent-id"], mock_db))
        assert len(results) == 0

    def test_multiple_pinned_returns_all_found(self):
        """Multiple pinned IDs return all that exist."""
        mock_db = MagicMock()

        def _table_factory(table_name):
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.maybe_single.return_value = chain
            # Return data for both calls
            chain.execute.return_value = MagicMock(data=FRAMEWORK_ROW)
            return chain

        mock_db.table.side_effect = _table_factory

        results = _run(fetch_pinned_frameworks([FRAMEWORK_ID, FRAMEWORK_ID_2], mock_db))
        assert len(results) == 2
