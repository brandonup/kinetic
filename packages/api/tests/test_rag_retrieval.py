"""
RAG retrieval pipeline test suite — KIN-249 (Sprint 2)

Tests the retrieval service at app/services/rag/retrieval.py.

Test plan (from build-order.md Sprint 2):
  - MMR selection: diverse chunks selected, redundant chunks de-prioritised
  - Threshold gating: chunks below similarity threshold excluded from injection
  - Citation assembly: returned chunks have correct source metadata

Framework: pytest + pytest-asyncio.
Coverage target: ≥80% on app/services/rag/retrieval/ module.
"""

from __future__ import annotations

import math
from typing import List
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from app.services.rag.retrieval import (
    MMR_TOP_K,
    SIMILARITY_THRESHOLD,
    RetrievalScope,
    RetrievedChunk,
    _apply_token_budget,
    _cosine_similarity,
    mmr_select,
    retrieve,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_embedding(seed: float, dims: int = 16) -> List[float]:
    """
    Generate a deterministic unit-normalised embedding from a scalar seed.

    Uses dims=16 to keep test vectors small and fast.
    The seed rotates by 2π/dims per component.
    """
    raw = [math.cos(seed + i * (2 * math.pi / dims)) for i in range(dims)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def _make_candidate(
    seed: float,
    similarity: float,
    document_id: str | None = None,
    text: str = "chunk text",
    dims: int = 16,
) -> dict:
    """Build a normalised candidate dict for MMR / retrieval tests."""
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
    }


# ---------------------------------------------------------------------------
# MMR selection
# ---------------------------------------------------------------------------


class TestMMRSelection:
    def test_mmr_returns_diverse_chunks(self):
        """
        Given a set of candidate chunks where several are near-duplicates, MMR should
        select a diverse subset rather than all high-scoring duplicates.

        Setup: 3 near-duplicate chunks (identical embeddings, high similarity score=0.9)
               + 3 diverse chunks with clearly different embeddings (similarity score=0.7).
        Expected: After selecting the first near-dupe, remaining near-dupes score BELOW
                  the diverse candidates in MMR (redundancy=1.0 kills them).
                  So in a top-4 selection, at most 1 near-dupe should appear.
        """
        # Three near-identical candidates — identical embedding vectors.
        # Seed=1.0 to avoid overlap with diverse seeds below.
        shared_emb = _make_embedding(1.0)
        near_dupes = []
        for _ in range(3):
            c = _make_candidate(1.0, similarity=0.9)
            c["embedding"] = shared_emb[:]  # force identical embeddings
            near_dupes.append(c)

        # Three diverse candidates spaced evenly around the embedding circle.
        # Seeds offset from 1.0 by multiples of 2π/5 — verified to have low similarity
        # with the near-dupe embedding (seeds 1.26, 2.54, 3.82).
        diverse_seeds = [1.0 + k * (2 * math.pi / 5) for k in [1, 2, 3]]
        diverse = [_make_candidate(s, similarity=0.7) for s in diverse_seeds]

        candidates = near_dupes + diverse
        query_embedding = _make_embedding(0.5)
        selected = mmr_select(query_embedding, candidates, top_k=4, lambda_=0.6)

        assert len(selected) == 4, f"Expected 4 selections, got {len(selected)}"

        # With identical near-dupe embeddings, after picking the first near-dupe:
        #   near-dupe MMR = 0.6 * 0.9 - 0.4 * 1.0 = 0.14
        #   diverse MMR   = 0.6 * 0.7 - 0.4 * sim(diverse, near-dupe) < 0.42
        # The diverse candidates win as long as they have lower redundancy.
        # Verify: at most 1 of the 3 near-dupes in the final selection.
        selected_ids = {c["chunk_id"] for c in selected}
        near_dupe_ids = {c["chunk_id"] for c in near_dupes}
        near_dupes_selected = len(selected_ids & near_dupe_ids)
        assert near_dupes_selected <= 1, (
            f"MMR selected {near_dupes_selected} near-duplicate chunks (expected ≤1) — "
            f"diversity pressure not working. "
            f"Scores: near-dupe MMR ≈ 0.14, diverse MMR ≈ 0.42 - redundancy"
        )


# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------


class TestTokenBudget:
    def test_mmr_respects_token_budget(self):
        """
        Token budget enforcement: chunks that would push total tokens over the floor
        are dropped from the tail of the result list.

        With mock tiktoken (len // 4), "a " * 4096 = 8192 chars = 2048 mock tokens.
        Default budget = max(RAG_MAX_TOKENS_FLOOR=2048, 0.15 * context_window=1000) = 2048.
        Three chunks at 2048 tokens each: first fills the budget exactly, second overflows.

        Expected: 1 chunk accepted, total_tokens <= 2048, len(result) < 3.
        """
        import app.services.rag.retrieval as retrieval_module
        from app.core.config import settings

        # 8192 chars / 4 = 2048 mock tokens per chunk
        chunks = [
            _make_candidate(float(i), similarity=0.8, text="a " * 4096)
            for i in range(3)
        ]
        for c in chunks:
            c["token_count"] = 0  # reset so _apply_token_budget recomputes

        result = retrieval_module._apply_token_budget(chunks, model_context_window=1000)

        budget = max(settings.RAG_MAX_TOKENS_FLOOR, int(1000 * settings.RAG_MAX_TOKENS_PERCENT))
        total_tokens = sum(c["token_count"] for c in result)

        assert len(result) < 3, (
            f"Expected fewer than 3 chunks after budget trim, got {len(result)}"
        )
        assert total_tokens <= budget, (
            f"Token budget violated: {total_tokens} > {budget}"
        )


# ---------------------------------------------------------------------------
# Threshold gating
# ---------------------------------------------------------------------------


class TestThresholdGating:
    @pytest.mark.asyncio
    async def test_chunks_below_threshold_are_excluded(self, seeded_chunks):
        """
        Chunks with cosine similarity below the configured threshold must not appear
        in the retrieval result, even if they are in the top-k by raw score.

        Expected: all returned chunks have similarity >= SIMILARITY_THRESHOLD.
        """
        project_id = uuid4()
        mock_supabase, chunk_rows = seeded_chunks(
            project_id=project_id,
            similarities=[0.5, 0.4, 0.2, 0.1],  # last two below threshold (0.3)
        )

        with patch(
            "app.services.ingestion.embedder.EmbeddingService.embed_batch",
            return_value=[[0.1] * 16],
        ):
            results = await retrieve(
                query_text="test query",
                scope=RetrievalScope.PROJECT_KB,
                scope_id=project_id,
                supabase=mock_supabase,
                model_context_window=100_000,
                similarity_threshold=SIMILARITY_THRESHOLD,
            )

        for chunk in results:
            assert chunk.similarity_score >= SIMILARITY_THRESHOLD, (
                f"Chunk {chunk.chunk_id} with score {chunk.similarity_score:.3f} "
                f"should have been excluded (threshold={SIMILARITY_THRESHOLD})"
            )

    @pytest.mark.asyncio
    async def test_no_chunks_returned_when_all_below_threshold(self):
        """
        When no chunks meet the similarity threshold (e.g. unrelated query), the
        retrieval layer must return an empty list — not a 500.

        Expected: result == [], no exception raised.
        """
        project_id = uuid4()

        mock_supabase = MagicMock()
        # Vector search returns rows all below threshold
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": str(uuid4()),
                    "document_id": str(uuid4()),
                    "text": "irrelevant content",
                    "embedding": _make_embedding(0.0),
                    "chunk_index": 0,
                    "section_path": None,
                    "page_range": None,
                    "similarity": 0.05,  # well below 0.3
                    "document_title": "Some Doc",
                    "document_type": "text/plain",
                }
            ]
        )

        with patch(
            "app.services.ingestion.embedder.EmbeddingService.embed_batch",
            return_value=[_make_embedding(1.0)],
        ):
            result = await retrieve(
                query_text="completely unrelated topic",
                scope=RetrievalScope.PROJECT_KB,
                scope_id=project_id,
                supabase=mock_supabase,
                model_context_window=100_000,
                similarity_threshold=SIMILARITY_THRESHOLD,
            )

        assert result == [], f"Expected empty list, got {result}"


# ---------------------------------------------------------------------------
# Citation assembly
# ---------------------------------------------------------------------------


class TestCitationAssembly:
    @pytest.mark.asyncio
    async def test_retrieved_chunks_include_source_metadata(self, seeded_chunks):
        """
        Each chunk in the retrieval result must carry correct source metadata:
        document_id, document_name, chunk_index, similarity_score.

        Expected: all result items have non-null document_id and document_name.
        """
        project_id = uuid4()
        mock_supabase, chunk_rows = seeded_chunks(
            project_id=project_id,
            similarities=[0.8, 0.7, 0.6],
        )

        with patch(
            "app.services.ingestion.embedder.EmbeddingService.embed_batch",
            return_value=[[0.1] * 16],
        ):
            results = await retrieve(
                query_text="test query",
                scope=RetrievalScope.PROJECT_KB,
                scope_id=project_id,
                supabase=mock_supabase,
                model_context_window=100_000,
            )

        assert len(results) > 0, "Expected at least one result"
        for chunk in results:
            assert isinstance(chunk, RetrievedChunk)
            assert chunk.document_id, f"document_id must be non-null, got: {chunk.document_id!r}"
            assert chunk.document_title, (
                f"document_title must be non-null, got: {chunk.document_title!r}"
            )
            assert chunk.chunk_index >= 0, f"chunk_index must be >= 0, got: {chunk.chunk_index}"
            assert 0.0 <= chunk.similarity_score <= 1.0, (
                f"similarity_score out of range: {chunk.similarity_score}"
            )

    @pytest.mark.asyncio
    async def test_citations_reference_correct_document(self, seeded_chunks):
        """
        Citation document_id must match the actual source document in the DB.
        No cross-document attribution.

        Expected: citation.document_id == chunk.document_id for all results.
        """
        project_id = uuid4()
        doc_id_a = str(uuid4())
        doc_id_b = str(uuid4())
        mock_supabase, chunk_rows = seeded_chunks(
            project_id=project_id,
            similarities=[0.9, 0.8],
            document_ids=[doc_id_a, doc_id_b],
        )

        with patch(
            "app.services.ingestion.embedder.EmbeddingService.embed_batch",
            return_value=[[0.1] * 16],
        ):
            results = await retrieve(
                query_text="test query",
                scope=RetrievalScope.PROJECT_KB,
                scope_id=project_id,
                supabase=mock_supabase,
                model_context_window=100_000,
            )

        assert len(results) > 0, "Expected at least one result"

        # Build ground truth: chunk_id → document_id from the seeded rows
        chunk_to_doc = {row["id"]: row["document_id"] for row in chunk_rows}

        for chunk in results:
            expected_doc_id = chunk_to_doc.get(chunk.chunk_id)
            if expected_doc_id is not None:
                assert chunk.document_id == expected_doc_id, (
                    f"Citation cross-attribution: chunk {chunk.chunk_id} "
                    f"attributed to doc {chunk.document_id}, "
                    f"expected {expected_doc_id}"
                )
