"""KIN-484 — Component C: recency scoring in the Python API retrieval path.

Covers:
* `recency_term` — piecewise-linear decay (ADR-009 boundaries).
* `recency_adjusted_score` derivation — additive, similarity_score immutable.
* Score-field discipline (design § Component C table):
    - Threshold gate uses raw similarity.
    - MMR first pick + relevance term use adjusted score (when enabled).
    - Token-budget eviction uses adjusted score (when enabled).
    - MMR diversity term unchanged.
* `RECENCY_ENABLED=False` byte-identical regression.
* 0-candidate edge case.

Curve constants are owned by ADR-009 — these tests pin the curve so a future
shape change must update both the ADR and the asserted boundary values.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import List
from unittest.mock import patch
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Helpers (mirrors test_rag_retrieval helpers — keep tests self-contained)
# ---------------------------------------------------------------------------


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _make_embedding(seed: float, dims: int = 16) -> List[float]:
    raw = [math.cos(seed + i * (2 * math.pi / dims)) for i in range(dims)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def _make_candidate(
    seed: float,
    similarity: float,
    *,
    effective_date: date | None = None,
    date_is_estimated: bool = False,
    document_id: str | None = None,
    text: str = "chunk text",
    dims: int = 16,
) -> dict:
    return {
        "chunk_id": str(uuid4()),
        "document_id": document_id or str(uuid4()),
        "document_title": f"Doc for seed {seed:.2f}",
        "document_type": "text/plain",
        "text": text,
        "chunk_index": 0,
        "section_path": "§1",
        "page_range": "1",
        "similarity_score": similarity,
        "embedding": _make_embedding(seed, dims),
        "token_count": 0,
        "effective_date": effective_date,
        "date_is_estimated": date_is_estimated,
    }


# ---------------------------------------------------------------------------
# recency_term — pure function, ADR-009 boundaries
# ---------------------------------------------------------------------------


class TestRecencyTermCurve:
    """ADR-009 piecewise-linear decay. Each boundary is hand-verifiable."""

    def test_today_is_plus_one(self):
        from app.services.rag.retrieval import recency_term

        today = _today_utc()
        assert recency_term(today, today) == pytest.approx(1.0)

    def test_137_days_is_plus_half(self):
        """Half-way to the 274d zero-crossing → +0.5."""
        from app.services.rag.retrieval import recency_term

        now = _today_utc()
        eff = now - timedelta(days=137)
        assert recency_term(eff, now) == pytest.approx(0.5, abs=1e-9)

    def test_274_days_is_zero(self):
        """Zero-crossing — exactly at the 9-month boundary."""
        from app.services.rag.retrieval import recency_term

        now = _today_utc()
        eff = now - timedelta(days=274)
        assert recency_term(eff, now) == pytest.approx(0.0, abs=1e-9)

    def test_502_days_is_minus_half(self):
        """Half-way between zero-crossing (274d) and floor (730d) → −0.5."""
        from app.services.rag.retrieval import recency_term

        now = _today_utc()
        eff = now - timedelta(days=502)
        assert recency_term(eff, now) == pytest.approx(-0.5, abs=1e-9)

    def test_730_days_is_minus_one(self):
        """Floor — 24 months."""
        from app.services.rag.retrieval import recency_term

        now = _today_utc()
        eff = now - timedelta(days=730)
        assert recency_term(eff, now) == pytest.approx(-1.0, abs=1e-9)

    def test_past_floor_is_clamped(self):
        """Beyond 730 days → still −1.0 (clamped)."""
        from app.services.rag.retrieval import recency_term

        now = _today_utc()
        eff = now - timedelta(days=5000)
        assert recency_term(eff, now) == pytest.approx(-1.0)

    def test_none_effective_date_yields_zero(self):
        """Fallback search path / unknown date → recency is a no-op."""
        from app.services.rag.retrieval import recency_term

        assert recency_term(None, _today_utc()) == 0.0

    def test_future_date_defensive_clamp(self):
        """Future date arrives only through a defect — defensive guard treats as age=0 → +1."""
        from app.services.rag.retrieval import recency_term

        now = _today_utc()
        eff = now + timedelta(days=30)
        result = recency_term(eff, now)
        # The done-when criterion is "future-clamped → ≥ 0"; specifically age=max(0, age)
        # yields recency_term(+1) (the age=0 value). Pin to the floor to make the
        # contract explicit.
        assert result >= 0.0
        assert result == pytest.approx(1.0)

    def test_curve_is_monotonic_nonincreasing(self):
        """Decay never reverses — older dates always score ≤ younger dates."""
        from app.services.rag.retrieval import recency_term

        now = _today_utc()
        previous = recency_term(now, now)
        for days in range(0, 1500, 25):
            eff = now - timedelta(days=days)
            current = recency_term(eff, now)
            assert current <= previous + 1e-9, (
                f"Curve not monotonic at age={days}d: previous={previous}, current={current}"
            )
            previous = current


# ---------------------------------------------------------------------------
# recency_adjusted_score — derivation + immutability of similarity_score
# ---------------------------------------------------------------------------


class TestRecencyAdjustedScore:
    def test_adjusted_score_equals_similarity_plus_weighted_term(self):
        """Per ADR-009: recency_adjusted_score = similarity + RECENCY_WEIGHT * recency_term."""
        from app.core.config import settings
        from app.services.rag.retrieval import compute_recency_adjusted_score, recency_term

        now = _today_utc()
        eff = now - timedelta(days=0)  # fresh → recency_term = +1.0
        adjusted = compute_recency_adjusted_score(
            similarity_score=0.70,
            effective_date=eff,
            now=now,
            weight=settings.RECENCY_WEIGHT,
        )
        expected = 0.70 + settings.RECENCY_WEIGHT * recency_term(eff, now)
        assert adjusted == pytest.approx(expected, abs=1e-9)

    def test_similarity_score_not_mutated(self):
        """`similarity_score` field on the candidate dict must stay raw cosine after scoring."""
        from app.core.config import settings
        from app.services.rag.retrieval import apply_recency_scoring

        now = _today_utc()
        candidate = _make_candidate(0.0, 0.55, effective_date=now)  # fresh
        original_similarity = candidate["similarity_score"]

        apply_recency_scoring([candidate], now=now, weight=settings.RECENCY_WEIGHT)

        assert candidate["similarity_score"] == original_similarity
        assert "recency_adjusted_score" in candidate
        assert candidate["recency_adjusted_score"] != original_similarity

    def test_none_effective_date_adjusts_to_zero_addition(self):
        """No date → recency_term=0 → adjusted == similarity."""
        from app.core.config import settings
        from app.services.rag.retrieval import compute_recency_adjusted_score

        adjusted = compute_recency_adjusted_score(
            similarity_score=0.42,
            effective_date=None,
            now=_today_utc(),
            weight=settings.RECENCY_WEIGHT,
        )
        assert adjusted == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# Score-field discipline — threshold gate uses raw, MMR/budget use adjusted
# ---------------------------------------------------------------------------


class TestScoreFieldDiscipline:
    """The design § Component C table is the contract these tests pin."""

    @pytest.mark.asyncio
    async def test_threshold_gate_uses_raw_similarity_recency_penalised_chunk_still_passes(
        self,
    ):
        """A genuinely-relevant chunk that is *old* (recency penalty) must still
        pass the similarity threshold — the gate must see the raw cosine, not the
        depressed `recency_adjusted_score`. Otherwise the recency feature would
        silently elevate the floor."""
        from app.services.rag.retrieval import RetrievalScope, retrieve
        from unittest.mock import MagicMock

        # similarity 0.32 — barely above 0.3. Old date → recency_term ≈ −1 →
        # adjusted ≈ 0.17. If the gate used the adjusted score, this chunk would
        # be excluded; the design says it must be retained.
        old_date = (_today_utc() - timedelta(days=2000)).isoformat()
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": str(uuid4()),
                    "document_id": str(uuid4()),
                    "text": "old but relevant content",
                    "embedding": _make_embedding(0.0),
                    "chunk_index": 0,
                    "section_path": None,
                    "page_range": None,
                    "similarity": 0.32,
                    "document_title": "Old Doc",
                    "document_type": "text/plain",
                    "document_date": old_date,
                    "document_created_at": old_date,
                }
            ]
        )

        with patch("app.core.config.settings.RECENCY_ENABLED", True), patch(
            "app.services.ingestion.embedder.EmbeddingService.embed_batch",
            return_value=[_make_embedding(0.0)],
        ), patch(
            "app.services.rag.retrieval._count_tokens",
            return_value=10,
        ):
            result = await retrieve(
                query_text="q",
                scope=RetrievalScope.PROJECT_KB,
                scope_id=uuid4(),
                supabase=mock_supabase,
                model_context_window=100_000,
            )

        assert len(result) == 1, (
            "Old-but-relevant chunk (raw=0.32) was excluded — threshold gate is "
            "using adjusted_score instead of raw similarity_score."
        )

    @pytest.mark.asyncio
    async def test_threshold_gate_uses_raw_similarity_recency_boosted_weak_chunk_still_fails(
        self,
    ):
        """A weak chunk that is *brand-new* (recency boost) must still fail the
        threshold — the boost must not sneak in a low-relevance chunk."""
        from app.services.rag.retrieval import RetrievalScope, retrieve
        from unittest.mock import MagicMock

        # similarity 0.20 — clearly below 0.3. Brand-new → recency_term = +1 →
        # adjusted = 0.35. If the gate used the adjusted score, this chunk would
        # incorrectly pass; the design says it must be excluded.
        fresh = _today_utc().isoformat()
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": str(uuid4()),
                    "document_id": str(uuid4()),
                    "text": "fresh but weakly-relevant",
                    "embedding": _make_embedding(0.0),
                    "chunk_index": 0,
                    "section_path": None,
                    "page_range": None,
                    "similarity": 0.20,
                    "document_title": "Fresh Doc",
                    "document_type": "text/plain",
                    "document_date": fresh,
                    "document_created_at": fresh,
                }
            ]
        )

        with patch("app.core.config.settings.RECENCY_ENABLED", True), patch(
            "app.services.ingestion.embedder.EmbeddingService.embed_batch",
            return_value=[_make_embedding(0.0)],
        ):
            result = await retrieve(
                query_text="q",
                scope=RetrievalScope.PROJECT_KB,
                scope_id=uuid4(),
                supabase=mock_supabase,
                model_context_window=100_000,
            )

        assert result == [], (
            "Fresh-but-weak chunk (raw=0.20) was retained — threshold gate is "
            "using adjusted_score instead of raw similarity_score."
        )

    def test_mmr_first_pick_uses_adjusted_score_when_enabled(self):
        """MMR's first pick is the highest scorer. With RECENCY_ENABLED, a
        slightly-less-similar but much-fresher chunk should win the first pick."""
        from app.core.config import settings
        from app.services.rag.retrieval import apply_recency_scoring, mmr_select

        now = _today_utc()
        # Chunk A: raw 0.80, stale (~24 months) → adjusted ≈ 0.80 + 0.15 * (-1) = 0.65
        a = _make_candidate(
            0.0, 0.80,
            effective_date=now - timedelta(days=730),
        )
        # Chunk B: raw 0.70, fresh (today) → adjusted ≈ 0.70 + 0.15 * 1.0 = 0.85
        b = _make_candidate(
            2.0, 0.70,
            effective_date=now,
        )
        candidates = [a, b]

        apply_recency_scoring(candidates, now=now, weight=settings.RECENCY_WEIGHT)
        # When the pipeline asks MMR to use adjusted_score, the first pick is B.
        selected = mmr_select(
            query_embedding=_make_embedding(0.5),
            candidates=candidates,
            top_k=1,
            lambda_=0.6,
            score_key="recency_adjusted_score",
        )
        assert selected[0]["chunk_id"] == b["chunk_id"], (
            "MMR first-pick did not use recency_adjusted_score — stale chunk won."
        )

    def test_mmr_first_pick_uses_raw_similarity_by_default(self):
        """Default behaviour (no `score_key` override) must remain raw similarity
        — protects the byte-identical regression and existing test suite."""
        from app.services.rag.retrieval import mmr_select

        now = _today_utc()
        # Same two candidates, no adjusted score computed.
        a = _make_candidate(0.0, 0.80, effective_date=now - timedelta(days=730))
        b = _make_candidate(2.0, 0.70, effective_date=now)

        selected = mmr_select(
            query_embedding=_make_embedding(0.5),
            candidates=[a, b],
            top_k=1,
            lambda_=0.6,
        )
        assert selected[0]["chunk_id"] == a["chunk_id"], (
            "MMR default score_key changed — byte-identical regression broken."
        )


# ---------------------------------------------------------------------------
# Byte-identical off-state regression — the highest-risk surface
# ---------------------------------------------------------------------------


class TestOffStateByteIdentical:
    @pytest.mark.asyncio
    async def test_off_state_byte_identical_chunk_ids_order_and_scores(
        self, seeded_chunks
    ):
        """With `RECENCY_ENABLED=False`, the retrieval pipeline returns the same
        chunk IDs, in the same order, with the same `similarity_score`s as it
        did before the feature shipped.

        Implementation: run twice. Once with the seed deterministic mocks, once
        with the same mocks plus a date column on every row. Both runs must
        agree on (chunk_id, score) pairs and order.
        """
        from app.services.rag.retrieval import RetrievalScope, retrieve
        from unittest.mock import MagicMock

        project_id = uuid4()
        # Run A — fixed similarities, no dates → simulates pre-feature behaviour.
        mock_a, _rows_a = seeded_chunks(
            project_id=project_id,
            similarities=[0.8, 0.7, 0.6, 0.55, 0.45],
        )

        with patch(
            "app.services.ingestion.embedder.EmbeddingService.embed_batch",
            return_value=[[0.1] * 16],
        ), patch(
            "app.services.rag.retrieval._count_tokens",
            return_value=10,
        ), patch(
            "app.core.config.settings.RECENCY_ENABLED", False
        ):
            results_a = await retrieve(
                query_text="q",
                scope=RetrievalScope.PROJECT_KB,
                scope_id=project_id,
                supabase=mock_a,
                model_context_window=100_000,
            )

        # Run B — same shape, every row now carries a date column. With
        # RECENCY_ENABLED=False the pipeline must ignore dates entirely.
        rows_b = []
        # Use the same id ordering as `_rows_a` so the IDs match exactly
        for i, row_a in enumerate(_rows_a):
            row_b = dict(row_a)
            # Mix of fresh and stale → would change ordering if RECENCY_ENABLED were True
            row_b["document_date"] = (
                _today_utc() - timedelta(days=i * 200)
            ).isoformat()
            row_b["document_created_at"] = row_b["document_date"]
            rows_b.append(row_b)
        mock_b = MagicMock()
        mock_b.rpc.return_value.execute.return_value = MagicMock(data=rows_b)

        with patch(
            "app.services.ingestion.embedder.EmbeddingService.embed_batch",
            return_value=[[0.1] * 16],
        ), patch(
            "app.services.rag.retrieval._count_tokens",
            return_value=10,
        ), patch(
            "app.core.config.settings.RECENCY_ENABLED", False
        ):
            results_b = await retrieve(
                query_text="q",
                scope=RetrievalScope.PROJECT_KB,
                scope_id=project_id,
                supabase=mock_b,
                model_context_window=100_000,
            )

        # The contract: with the flag OFF, the dates must not change anything.
        a_signature = [(c.chunk_id, c.similarity_score) for c in results_a]
        b_signature = [(c.chunk_id, c.similarity_score) for c in results_b]
        assert a_signature == b_signature, (
            "RECENCY_ENABLED=False produced different output once dates were "
            "added — off-state regression broken."
        )


# ---------------------------------------------------------------------------
# 0-candidate edge case
# ---------------------------------------------------------------------------


class TestZeroCandidateEdgeCase:
    def test_apply_recency_scoring_on_empty_list(self):
        from app.core.config import settings
        from app.services.rag.retrieval import apply_recency_scoring

        # No raise; no effect.
        apply_recency_scoring([], now=_today_utc(), weight=settings.RECENCY_WEIGHT)

    @pytest.mark.asyncio
    async def test_retrieve_empty_vector_search_no_crash(self):
        from app.services.rag.retrieval import RetrievalScope, retrieve
        from unittest.mock import MagicMock

        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=[])

        with patch(
            "app.services.ingestion.embedder.EmbeddingService.embed_batch",
            return_value=[_make_embedding(0.0)],
        ), patch(
            "app.core.config.settings.RECENCY_ENABLED", True
        ):
            result = await retrieve(
                query_text="q",
                scope=RetrievalScope.PROJECT_KB,
                scope_id=uuid4(),
                supabase=mock_supabase,
                model_context_window=100_000,
            )

        assert result == []
