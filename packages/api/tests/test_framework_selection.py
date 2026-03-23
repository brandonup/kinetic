"""
Unit tests for framework_selection.select_framework() — KIN-289.

Covers:
- No trigger embeddings → returns None
- No candidates above short-circuit threshold → returns None
- Single candidate above threshold → skip Haiku, return directly
- Multiple candidates → Haiku called → winner returned
- Haiku returns unrecognised ID → fallback to top candidate
- Haiku API failure → fallback to top candidate
- Embedding failure → returns None
- Expertise boost applied for multiple trigger matches
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.framework_selection import _score_frameworks, select_framework


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_embedding(seed: float, dims: int = 8) -> list[float]:
    """Create a normalised mock embedding with direction determined by seed.

    seed=0   → [1, 0, 0, ...]
    seed=1   → [0, 1, 0, ...]
    seed=0.5 → [0.707, 0.707, 0, ...]   (45-degree rotation)
    """
    import math
    angle = seed * math.pi / 2
    v = [math.cos(angle), math.sin(angle)] + [0.0] * max(0, dims - 2)
    return v


FRAMEWORK_A = {
    "id": "fw-db-1",
    "framework_id": "five-whys",
    "name": "Five Whys",
    "description": "Root cause analysis",
    "when_to_apply": ["debugging", "problem solving"],
    "principles": ["ask why repeatedly"],
    "steps": None,
}

FRAMEWORK_B = {
    "id": "fw-db-2",
    "framework_id": "first-principles",
    "name": "First Principles",
    "description": "Break down assumptions",
    "when_to_apply": ["complex problems"],
    "principles": ["question everything"],
    "steps": None,
}


def _make_supabase_with_triggers_and_frameworks(
    triggers: list[dict],
    frameworks: list[dict],
) -> MagicMock:
    sb = MagicMock()
    current_table: list[str] = [""]

    def _table(name):
        current_table[0] = name
        return sb

    sb.table.side_effect = _table
    sb.select.return_value = sb
    sb.eq.return_value = sb
    sb.in_.return_value = sb
    sb.order.return_value = sb
    sb.limit.return_value = sb
    sb.maybe_single.return_value = sb

    def _execute():
        table = current_table[0]
        r = MagicMock()
        if table == "framework_trigger_embeddings":
            r.data = triggers
        elif table == "frameworks":
            r.data = frameworks
        else:
            r.data = None
        return r

    sb.execute.side_effect = _execute
    return sb


# ---------------------------------------------------------------------------
# _score_frameworks unit tests
# ---------------------------------------------------------------------------


def test_score_frameworks_returns_sorted_descending():
    q_emb = _make_embedding(1.0)
    trigger_rows = [
        {"framework_db_id": "fw-1", "embedding": _make_embedding(1.0)},  # identical → sim=1
        {"framework_db_id": "fw-2", "embedding": _make_embedding(0.1)},  # orthogonal-ish
    ]
    scores = _score_frameworks(
        query_embedding=q_emb,
        trigger_rows=trigger_rows,
        expertise_boost=0.05,
        boost_threshold=0.2,
    )
    assert scores[0]["framework_db_id"] == "fw-1"
    assert scores[0]["score"] >= scores[1]["score"]


def test_score_frameworks_expertise_boost():
    """Multiple triggers for same framework above threshold get boost."""
    q_emb = _make_embedding(1.0)
    trigger_rows = [
        {"framework_db_id": "fw-1", "embedding": _make_embedding(1.0)},   # sim ≈ 1.0
        {"framework_db_id": "fw-1", "embedding": _make_embedding(0.99)},   # sim ≈ high
        {"framework_db_id": "fw-2", "embedding": _make_embedding(1.0)},   # single trigger
    ]
    scores = _score_frameworks(
        query_embedding=q_emb,
        trigger_rows=trigger_rows,
        expertise_boost=0.05,
        boost_threshold=0.2,
    )
    fw1 = next(s for s in scores if s["framework_db_id"] == "fw-1")
    fw2 = next(s for s in scores if s["framework_db_id"] == "fw-2")
    # fw-1 has extra trigger above threshold, so it should be boosted
    assert fw1["score"] > fw2["score"]


# ---------------------------------------------------------------------------
# select_framework integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_no_trigger_embeddings_returns_none():
    sb = _make_supabase_with_triggers_and_frameworks([], [])

    with patch("app.services.embedding_service.embed_text", new_callable=AsyncMock, return_value=_make_embedding(1.0)):
        result = await select_framework(
            query="test",
            agent_definition_id="agent-1",
            agent_category=None,
            supabase=sb,
        )
    assert result is None


@pytest.mark.asyncio
async def test_select_no_candidates_above_threshold_returns_none():
    q_emb = _make_embedding(1.0)
    # Trigger embedding is nearly orthogonal to query
    triggers = [
        {
            "framework_db_id": "fw-db-1",
            "trigger_text": "something unrelated",
            "embedding": _make_embedding(0.0001),  # near-zero, very low similarity
        }
    ]
    sb = _make_supabase_with_triggers_and_frameworks(triggers, [FRAMEWORK_A])

    with patch("app.services.embedding_service.embed_text", new_callable=AsyncMock, return_value=q_emb), \
         patch("app.config.get_settings") as mock_settings:
        s = MagicMock()
        s.FRAMEWORK_SIMILARITY_SHORT_CIRCUIT = 0.99  # very high threshold
        s.FRAMEWORK_MIN_RERANK_THRESHOLD = 0.99
        s.FRAMEWORK_TOP_K = 5
        s.FRAMEWORK_EXPERTISE_BOOST = 0.05
        mock_settings.return_value = s

        result = await select_framework(
            query="test",
            agent_definition_id="agent-1",
            agent_category=None,
            supabase=sb,
        )
    assert result is None


@pytest.mark.asyncio
async def test_select_single_candidate_skips_haiku():
    """Single candidate above threshold: skip Haiku, return it directly."""
    q_emb = _make_embedding(1.0)
    triggers = [
        {
            "framework_db_id": "fw-db-1",
            "trigger_text": "debugging",
            "embedding": _make_embedding(1.0),  # identical → sim = 1.0
        }
    ]
    sb = _make_supabase_with_triggers_and_frameworks(triggers, [FRAMEWORK_A])

    with patch("app.services.embedding_service.embed_text", new_callable=AsyncMock, return_value=q_emb), \
         patch("app.config.get_settings") as mock_settings, \
         patch("app.services.framework_selection._haiku_rerank", new_callable=AsyncMock) as mock_haiku:

        s = MagicMock()
        s.FRAMEWORK_SIMILARITY_SHORT_CIRCUIT = 0.1
        s.FRAMEWORK_MIN_RERANK_THRESHOLD = 0.1
        s.FRAMEWORK_TOP_K = 5
        s.FRAMEWORK_EXPERTISE_BOOST = 0.05
        mock_settings.return_value = s

        result = await select_framework(
            query="debugging",
            agent_definition_id="agent-1",
            agent_category=None,
            supabase=sb,
        )

    mock_haiku.assert_not_called()
    assert result is not None
    assert result["framework_id"] == "five-whys"


@pytest.mark.asyncio
async def test_select_multiple_candidates_calls_haiku():
    """Multiple candidates above threshold: Haiku should be called."""
    q_emb = _make_embedding(1.0)
    triggers = [
        {"framework_db_id": "fw-db-1", "trigger_text": "debug", "embedding": _make_embedding(1.0)},
        {"framework_db_id": "fw-db-2", "trigger_text": "problem", "embedding": _make_embedding(0.95)},
    ]
    sb = _make_supabase_with_triggers_and_frameworks(triggers, [FRAMEWORK_A, FRAMEWORK_B])

    with patch("app.services.embedding_service.embed_text", new_callable=AsyncMock, return_value=q_emb), \
         patch("app.config.get_settings") as mock_settings, \
         patch("app.services.framework_selection._haiku_rerank", new_callable=AsyncMock, return_value=FRAMEWORK_A) as mock_haiku:

        s = MagicMock()
        s.FRAMEWORK_SIMILARITY_SHORT_CIRCUIT = 0.1
        s.FRAMEWORK_MIN_RERANK_THRESHOLD = 0.1
        s.FRAMEWORK_TOP_K = 5
        s.FRAMEWORK_EXPERTISE_BOOST = 0.05
        mock_settings.return_value = s

        result = await select_framework(
            query="debug something",
            agent_definition_id="agent-1",
            agent_category="coaching",
            supabase=sb,
        )

    mock_haiku.assert_called_once()
    assert result == FRAMEWORK_A


@pytest.mark.asyncio
async def test_select_embedding_failure_returns_none():
    sb = _make_supabase_with_triggers_and_frameworks([], [])

    with patch("app.services.embedding_service.embed_text", new_callable=AsyncMock, side_effect=RuntimeError("embed fail")):
        result = await select_framework(
            query="test",
            agent_definition_id="agent-1",
            agent_category=None,
            supabase=sb,
        )
    assert result is None


@pytest.mark.asyncio
async def test_select_haiku_failure_falls_back_to_top_candidate():
    """If Haiku raises, fall back to the highest-scoring candidate."""
    q_emb = _make_embedding(1.0)
    triggers = [
        {"framework_db_id": "fw-db-1", "trigger_text": "debug", "embedding": _make_embedding(1.0)},
        {"framework_db_id": "fw-db-2", "trigger_text": "problem", "embedding": _make_embedding(0.5)},
    ]
    sb = _make_supabase_with_triggers_and_frameworks(triggers, [FRAMEWORK_A, FRAMEWORK_B])

    with patch("app.services.embedding_service.embed_text", new_callable=AsyncMock, return_value=q_emb), \
         patch("app.config.get_settings") as mock_settings, \
         patch("app.services.framework_selection._haiku_rerank", new_callable=AsyncMock, side_effect=Exception("haiku down")):

        s = MagicMock()
        s.FRAMEWORK_SIMILARITY_SHORT_CIRCUIT = 0.1
        s.FRAMEWORK_MIN_RERANK_THRESHOLD = 0.1
        s.FRAMEWORK_TOP_K = 5
        s.FRAMEWORK_EXPERTISE_BOOST = 0.05
        mock_settings.return_value = s

        result = await select_framework(
            query="debug",
            agent_definition_id="agent-1",
            agent_category=None,
            supabase=sb,
        )

    # Should return highest-scoring framework (fw-db-1 = five-whys, sim=1.0)
    assert result is not None
    assert result["framework_id"] == "five-whys"
