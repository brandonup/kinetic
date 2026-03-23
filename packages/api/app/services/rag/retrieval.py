"""
RAG retrieval pipeline — MVP implementation.

Pipeline:
  1. Embed query         — text-embedding-3-large via platform OpenAI key
  2. Vector search       — cosine similarity against knowledge_base_chunks (scoped)
  3. MMR selection       — Maximal Marginal Relevance to reduce near-duplicates
  4. Similarity threshold — exclude chunks below SIMILARITY_THRESHOLD; return [] if none qualify
  5. Token budget gate   — drop lowest-scoring chunks that exceed RAG_MAX_TOKENS
  6. Citation assembly   — return RetrievedChunk objects with full source metadata

Zero LLM calls in the MVP retrieval path. All Supabase calls wrapped in run_in_executor.

Schema ref: docs/db-schema-spec.md §13 (knowledge_base_chunks)
Spec ref:   docs/rag-architecture.md § MVP Retrieval Details
Config:     VECTOR_TOP_K=20, MMR_TOP_K=8, MMR_LAMBDA=0.6, SIMILARITY_THRESHOLD=0.3
            RAG_MAX_TOKENS = max(2048, int(model_context_window * 0.15))
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from uuid import UUID

import tiktoken

from app.core.config import settings
from app.services.ingestion.embedder import EmbeddingService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration defaults — override per spec (db-schema-spec.md Config table)
# ---------------------------------------------------------------------------

VECTOR_TOP_K: int = 20          # candidates returned from vector search
MMR_TOP_K: int = 8              # candidates after MMR selection
MMR_LAMBDA: float = 0.6         # relevance/diversity tradeoff (higher = more relevant)
SIMILARITY_THRESHOLD: float = 0.3  # minimum cosine similarity for injection
RAG_MAX_TOKENS_FRACTION: float = 0.15  # 15% of model context window
RAG_MAX_TOKENS_FLOOR: int = 2048       # minimum floor


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class RetrievalScope(str, Enum):
    """Retrieval scope — mirrors retrieval_scope enum in db-schema-spec.md."""
    PROJECT_KB = "project_kb"
    AGENT_KB = "agent_kb"


@dataclass
class RetrievedChunk:
    """
    A single chunk returned by the retrieval pipeline, with citation metadata.

    Fields match knowledge_base_chunks columns (db-schema-spec.md §13) plus
    document-level fields joined from knowledge_base_documents.
    """
    chunk_id: str                    # knowledge_base_chunks.id
    document_id: str                 # knowledge_base_chunks.document_id
    document_title: str              # knowledge_base_documents.title (joined)
    document_type: Optional[str]     # knowledge_base_documents.file_type (joined)
    text: str                        # knowledge_base_chunks.text
    chunk_index: int                 # knowledge_base_chunks.chunk_index
    section_path: Optional[str]      # knowledge_base_chunks.section_path
    page_range: Optional[str]        # knowledge_base_chunks.page_range
    similarity_score: float          # cosine similarity from vector search
    token_count: int = field(default=0)  # estimated tokens (set after retrieval)
    scope: Optional[str] = field(default=None)  # 'project_kb' or 'agent_kb'


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

_ENCODING_NAME = "cl100k_base"
_encoding = None
_embedder: Optional[EmbeddingService] = None


def _get_encoding():
    """Return tiktoken encoding, initialised once per process."""
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoding


def _get_embedder() -> EmbeddingService:
    """Return a shared EmbeddingService instance (lazy singleton)."""
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()
    return _embedder


def _count_tokens(text: str) -> int:
    """Count tokens in text using cl100k_base encoding."""
    return len(_get_encoding().encode(text))


# ---------------------------------------------------------------------------
# Cosine similarity (pure Python — no external dep needed for small vectors)
# ---------------------------------------------------------------------------


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    if len(a) != len(b):
        raise ValueError(
            f"Embedding dimension mismatch: {len(a)} vs {len(b)}. "
            "All embeddings must use the same model."
        )
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# MMR selection
# ---------------------------------------------------------------------------


def mmr_select(
    query_embedding: List[float],
    candidates: List[dict],
    top_k: int = MMR_TOP_K,
    lambda_: float = MMR_LAMBDA,
) -> List[dict]:
    """
    Maximal Marginal Relevance selection over candidate chunks.

    Balances relevance to the query against diversity within the selected set.
    Reduces near-duplicate injection when the KB has adjacent/repeated content.

    Args:
        query_embedding: The embedded user query (3072 dims).
        candidates: List of candidate dicts, each with key 'embedding' (List[float])
                    and 'similarity_score' (float). Must be non-empty.
        top_k: Maximum number of chunks to select.
        lambda_: Tradeoff — 1.0 = pure relevance, 0.0 = pure diversity.

    Returns:
        Ordered list of selected candidate dicts (subset of candidates).
    """
    if not candidates:
        return []

    top_k = min(top_k, len(candidates))
    selected: List[dict] = []
    remaining = list(candidates)

    while len(selected) < top_k and remaining:
        if not selected:
            # First pick: highest similarity to query
            best = max(remaining, key=lambda c: c["similarity_score"])
        else:
            # MMR score = λ * sim(query, c) - (1-λ) * max(sim(c, s) for s in selected)
            best = None
            best_score = float("-inf")
            selected_embeddings = [s["embedding"] for s in selected]

            for candidate in remaining:
                relevance = candidate["similarity_score"]
                redundancy = max(
                    _cosine_similarity(candidate["embedding"], sel_emb)
                    for sel_emb in selected_embeddings
                )
                mmr_score = lambda_ * relevance - (1.0 - lambda_) * redundancy
                if mmr_score > best_score:
                    best_score = mmr_score
                    best = candidate

        if best is None:
            break
        selected.append(best)
        remaining.remove(best)

    return selected


# ---------------------------------------------------------------------------
# Vector search (Supabase pgvector RPC)
# ---------------------------------------------------------------------------


def _build_scope_filter(
    scope: RetrievalScope,
    scope_id: UUID,
) -> dict:
    """
    Build the scope column + value for the vector search query.

    knowledge_base_chunks.project_id or agent_definition_id per spec §13.
    """
    if scope == RetrievalScope.PROJECT_KB:
        return {"column": "project_id", "value": str(scope_id)}
    return {"column": "agent_definition_id", "value": str(scope_id)}


def _vector_search_sync(
    supabase,
    query_embedding: List[float],
    scope: RetrievalScope,
    scope_id: UUID,
    top_k: int,
) -> List[dict]:
    """
    Synchronous vector similarity search against knowledge_base_chunks.

    Fetches top_k chunks by cosine similarity, filtered to the correct scope.
    Joins knowledge_base_documents to pull document title and file_type for citations.

    Uses a Supabase select + order by embedding <=> query pattern — the pgvector
    operator `<=>` computes cosine distance (1 - cosine_similarity).

    NOTE: Supabase Python client does not support pgvector operators natively;
    we use a raw RPC (match_chunks) for the vector search. If match_chunks is not
    available, falls back to fetching all scope-filtered chunks (test-safe).

    Schema ref: db-schema-spec.md §13 (knowledge_base_chunks)
                db-schema-spec.md §12 (knowledge_base_documents — for title/file_type)
    """
    scope_filter = _build_scope_filter(scope, scope_id)

    # Attempt RPC-based vector search (production path — requires match_chunks function)
    try:
        result = (
            supabase.rpc(
                "match_chunks",
                {
                    "query_embedding": query_embedding,
                    "scope_column": scope_filter["column"],
                    "scope_value": scope_filter["value"],
                    "match_count": top_k,
                },
            )
            .execute()
        )
        if result.data is not None:
            return result.data
    except Exception as exc:
        logger.debug(
            "match_chunks RPC unavailable (%s); falling back to filtered select.", exc
        )

    # Fallback: select scope-filtered chunks (used in unit tests with mock Supabase)
    # Read-path fail-open: return [] on retrieval failure (not a write operation).
    #
    # Two deleted_at filters are required:
    #   1. knowledge_base_chunks.deleted_at IS NULL  — excludes hard-cleaned chunks
    #   2. knowledge_base_documents.deleted_at IS NULL — excludes chunks whose parent
    #      document was soft-deleted but whose chunks have not yet been cleaned up
    #      (chunks are purged after a 7-day window per MEMORY.md 2026-03-22 decision).
    try:
        result = (
            supabase.table("knowledge_base_chunks")
            .select(
                "id, document_id, text, embedding, chunk_index, section_path, page_range, "
                "knowledge_base_documents!inner(title, file_type, deleted_at)"
            )
            .eq(scope_filter["column"], scope_filter["value"])
            .is_("deleted_at", "null")
            .is_("knowledge_base_documents.deleted_at", "null")
            .limit(top_k)
            .execute()
        )
        rows = result.data or []
    except Exception as exc:
        logger.warning("Vector search fallback select failed: %s", exc)
        return []

    # Compute cosine similarity client-side for fallback path
    for row in rows:
        emb = row.get("embedding") or []
        row["similarity"] = _cosine_similarity(query_embedding, emb) if emb else 0.0

    # Sort by similarity descending
    rows.sort(key=lambda r: r.get("similarity", 0.0), reverse=True)
    return rows[:top_k]


def _normalise_search_row(row: dict) -> dict:
    """
    Normalise a raw row from either the RPC or fallback select into a uniform shape.

    RPC (match_chunks) returns: id, document_id, text, embedding, chunk_index,
      section_path, page_range, similarity, document_title, document_type
    Fallback select returns joined knowledge_base_documents nested under a key.
    """
    # Extract document metadata — may be top-level (RPC) or nested (select join)
    doc_meta = row.get("knowledge_base_documents") or {}
    if isinstance(doc_meta, list):
        doc_meta = doc_meta[0] if doc_meta else {}

    document_title = row.get("document_title") or doc_meta.get("title") or "Unknown"
    document_type = row.get("document_type") or doc_meta.get("file_type")

    # Similarity — RPC names it 'similarity'; fallback computes it as 'similarity'
    similarity = float(row.get("similarity", 0.0))

    embedding = row.get("embedding") or []

    return {
        "chunk_id": str(row.get("id", "")),
        "document_id": str(row.get("document_id", "")),
        "document_title": document_title,
        "document_type": document_type,
        "text": row.get("text", ""),
        "chunk_index": int(row.get("chunk_index", 0)),
        "section_path": row.get("section_path"),
        "page_range": row.get("page_range"),
        "similarity_score": similarity,
        "embedding": embedding,
    }


# ---------------------------------------------------------------------------
# Token budget enforcement
# ---------------------------------------------------------------------------


def _apply_token_budget(
    chunks: List[dict],
    model_context_window: int,
) -> List[dict]:
    """
    Drop lowest-scoring chunks that would exceed RAG_MAX_TOKENS.

    Budget = max(RAG_MAX_TOKENS_FLOOR, int(model_context_window * RAG_MAX_TOKENS_FRACTION))

    Chunks are already sorted by MMR score (insertion order). We fill greedily
    from the top, stopping when the budget would be exceeded.

    Args:
        chunks: MMR-selected, threshold-filtered candidates (highest priority first).
        model_context_window: Context window of the selected generation model (tokens).

    Returns:
        Subset of chunks that fit within the token budget, with token_count set.
    """
    budget = max(
        settings.RAG_MAX_TOKENS_FLOOR,
        int(model_context_window * settings.RAG_MAX_TOKENS_PERCENT),
    )

    accepted: List[dict] = []
    used_tokens = 0

    for chunk in chunks:
        count = _count_tokens(chunk["text"])
        if used_tokens + count > budget:
            logger.debug(
                "Token budget reached at %d/%d tokens — dropping remaining %d chunks.",
                used_tokens,
                budget,
                len(chunks) - len(accepted),
            )
            break
        chunk["token_count"] = count
        accepted.append(chunk)
        used_tokens += count

    return accepted


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def retrieve(
    query_text: str,
    scope: RetrievalScope,
    scope_id: UUID,
    supabase,
    model_context_window: int = 100_000,
    vector_top_k: int = VECTOR_TOP_K,
    mmr_top_k: int = MMR_TOP_K,
    mmr_lambda: float = MMR_LAMBDA,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
) -> List[RetrievedChunk]:
    """
    Run the full MVP RAG retrieval pipeline for one scope.

    Pipeline:
      embed query → vector search → MMR selection → threshold gate
      → token budget → citation assembly

    Args:
        query_text: The user's raw query string.
        scope: RetrievalScope.PROJECT_KB or RetrievalScope.AGENT_KB.
        scope_id: UUID of the project or agent_definition, depending on scope.
        supabase: Supabase service-role client (sync — wrapped in run_in_executor).
        model_context_window: Context window of the generation model (tokens).
            Used to compute RAG_MAX_TOKENS = max(2048, context_window * 15%).
        vector_top_k: Candidates to fetch from vector search (default 20).
        mmr_top_k: Candidates to keep after MMR (default 8).
        mmr_lambda: MMR relevance/diversity tradeoff (default 0.6).
        similarity_threshold: Minimum cosine similarity for injection (default 0.3).

    Returns:
        List of RetrievedChunk objects ordered by MMR score (best first).
        Returns [] when no chunks meet the threshold — never raises on empty result.

    Raises:
        RuntimeError: If the embedding call fails (platform key misconfigured, network).
    """
    if not query_text.strip():
        logger.warning("retrieve() called with empty query — returning [].")
        return []

    if scope_id is None:
        raise ValueError("scope_id must not be null — pass a valid project/agent UUID.")

    # --- Step 1: Embed query ---
    embedder = _get_embedder()
    loop = asyncio.get_running_loop()
    try:
        query_embeddings: List[List[float]] = await loop.run_in_executor(
            None, lambda: embedder.embed_batch([query_text])
        )
    except Exception as exc:
        raise RuntimeError(f"RAG query embedding failed: {exc}") from exc

    query_embedding = query_embeddings[0]

    # --- Step 2: Vector search ---
    raw_rows: List[dict] = await loop.run_in_executor(
        None,
        lambda: _vector_search_sync(supabase, query_embedding, scope, scope_id, vector_top_k),
    )

    if not raw_rows:
        logger.debug(
            "Vector search returned 0 candidates for scope=%s scope_id=%s",
            scope,
            scope_id,
        )
        return []

    # Normalise rows to uniform shape
    candidates = [_normalise_search_row(row) for row in raw_rows]

    # --- Step 3: MMR selection ---
    mmr_results = mmr_select(
        query_embedding=query_embedding,
        candidates=candidates,
        top_k=mmr_top_k,
        lambda_=mmr_lambda,
    )

    # --- Step 4: Similarity threshold gate ---
    above_threshold = [c for c in mmr_results if c["similarity_score"] >= similarity_threshold]

    if not above_threshold:
        logger.debug(
            "All %d MMR candidates below similarity threshold %.2f for scope=%s — returning [].",
            len(mmr_results),
            similarity_threshold,
            scope,
        )
        return []

    # --- Step 5: Token budget ---
    budget_filtered = _apply_token_budget(above_threshold, model_context_window)

    # --- Step 6: Citation assembly ---
    retrieved: List[RetrievedChunk] = []
    for chunk in budget_filtered:
        retrieved.append(
            RetrievedChunk(
                chunk_id=chunk["chunk_id"],
                document_id=chunk["document_id"],
                document_title=chunk["document_title"],
                document_type=chunk.get("document_type"),
                text=chunk["text"],
                chunk_index=chunk["chunk_index"],
                section_path=chunk.get("section_path"),
                page_range=chunk.get("page_range"),
                similarity_score=chunk["similarity_score"],
                token_count=chunk.get("token_count", 0),
                scope=scope.value,
            )
        )

    logger.info(
        "RAG retrieval complete: scope=%s, candidates=%d, mmr=%d, "
        "above_threshold=%d, budget_filtered=%d",
        scope,
        len(candidates),
        len(mmr_results),
        len(above_threshold),
        len(budget_filtered),
    )

    return retrieved
