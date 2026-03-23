"""
RAG retrieval service — KIN-258, used by context stack L8 + L9.

Pipeline (MVP, zero LLM calls):
  embed query → vector search (cosine similarity) → MMR → threshold gate → format

Spec ref:  docs/rag-architecture.md
ADR ref:   docs/adr-002-rag-retrieval-pipeline.md
Schema:    docs/db-schema-spec.md §13 (knowledge_base_chunks)
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


async def retrieve_for_project(
    query: str,
    project_id: str,
    model_context_window: int,
    supabase: Any,
) -> str:
    """Retrieve and format chunks for a project KB (Layer 8).

    Returns formatted context string, or empty string if no KB / no matches.
    """
    kb_id = await _get_kb_id(supabase, project_id=project_id)
    if not kb_id:
        return ""
    return await _retrieve(
        query=query,
        scope_filter={"project_id": project_id},
        kb_label="Project Knowledge Base",
        model_context_window=model_context_window,
        supabase=supabase,
    )


async def retrieve_for_agent(
    query: str,
    agent_definition_id: str,
    model_context_window: int,
    supabase: Any,
) -> str:
    """Retrieve and format chunks for an agent KB (Layer 9).

    Returns formatted context string, or empty string if no KB / no matches.
    """
    kb_id = await _get_kb_id(supabase, agent_definition_id=agent_definition_id)
    if not kb_id:
        return ""
    return await _retrieve(
        query=query,
        scope_filter={"agent_definition_id": agent_definition_id},
        kb_label="Agent Knowledge Base",
        model_context_window=model_context_window,
        supabase=supabase,
    )


# ---------------------------------------------------------------------------
# Core retrieval pipeline
# ---------------------------------------------------------------------------


async def _get_kb_id(
    supabase: Any,
    *,
    project_id: Optional[str] = None,
    agent_definition_id: Optional[str] = None,
) -> Optional[str]:
    """Return the knowledge_base id for a project or agent, or None if none exists."""
    loop = asyncio.get_running_loop()
    query = supabase.table("knowledge_bases").select("id")
    if project_id:
        query = query.eq("project_id", project_id)
    elif agent_definition_id:
        query = query.eq("agent_definition_id", agent_definition_id)
    else:
        return None

    result = await loop.run_in_executor(None, lambda: query.maybe_single().execute())
    return result.data["id"] if result.data else None


async def _retrieve(
    *,
    query: str,
    scope_filter: dict,
    kb_label: str,
    model_context_window: int,
    supabase: Any,
) -> str:
    from app.config import get_settings
    from app.services.embedding_service import embed_text

    settings = get_settings()
    loop = asyncio.get_running_loop()

    # Embed query
    try:
        query_embedding = await embed_text(query)
    except Exception:
        logger.exception("Embedding failed for RAG query, skipping %s", kb_label)
        return ""

    # Vector search via pgvector RPC
    try:
        scope_key, scope_val = next(iter(scope_filter.items()))
        rpc_result = await loop.run_in_executor(
            None,
            lambda: supabase.rpc(
                "match_chunks",
                {
                    "query_embedding": query_embedding,
                    "scope_key": scope_key,
                    "scope_val": scope_val,
                    "match_count": settings.VECTOR_TOP_K,
                    "similarity_threshold": 0.0,  # filter in Python after MMR
                },
            ).execute(),
        )
        candidates: list[dict] = rpc_result.data or []
    except Exception:
        logger.exception("Vector search failed for %s", kb_label)
        return ""

    if not candidates:
        return ""

    # MMR selection
    selected = _mmr_select(
        candidates=candidates,
        lmbda=settings.MMR_LAMBDA,
        top_k=settings.MMR_TOP_K,
    )

    # Similarity threshold gate
    above_threshold = [
        c for c in selected if c.get("similarity", 0) >= settings.SIMILARITY_THRESHOLD
    ]
    if not above_threshold:
        return ""

    # Token budget — RAG_MAX_TOKENS = 15% of context window, floor 2048
    rag_max_tokens = max(2048, int(model_context_window * 0.15))
    chunks = _apply_token_budget(above_threshold, rag_max_tokens)

    return _format_chunks(chunks, kb_label)


def _mmr_select(
    candidates: list[dict],
    lmbda: float,
    top_k: int,
) -> list[dict]:
    """
    Maximal Marginal Relevance selection.

    lmbda: 0 = diversity only, 1 = relevance only (0.6 default per ADR-002)
    """
    if not candidates:
        return []

    import numpy as np

    embeddings = [c.get("embedding") or [] for c in candidates]

    # Convert to numpy array for cosine computations; skip if embeddings absent
    try:
        emb_matrix = np.array(embeddings, dtype=float)
    except Exception:
        # No embeddings in result (RPC may not return them) — return by score
        return sorted(candidates, key=lambda c: c.get("similarity", 0), reverse=True)[:top_k]

    scores = np.array([c.get("similarity", 0) for c in candidates], dtype=float)
    n = len(candidates)
    selected_indices: list[int] = []
    remaining = list(range(n))

    for _ in range(min(top_k, n)):
        if not remaining:
            break
        if not selected_indices:
            # First: pick highest relevance score
            idx = max(remaining, key=lambda i: scores[i])
        else:
            # MMR: balance relevance vs. diversity from already-selected set
            best_idx = None
            best_mmr = -float("inf")
            sel_embs = emb_matrix[selected_indices]
            for i in remaining:
                rel = lmbda * scores[i]
                # Max cosine similarity to any already-selected item
                if len(sel_embs) > 0 and len(emb_matrix[i]) > 0:
                    try:
                        sims = _cosine_sim_batch(emb_matrix[i], sel_embs)
                        div = (1 - lmbda) * float(np.max(sims))
                    except Exception:
                        div = 0.0
                else:
                    div = 0.0
                mmr = rel - div
                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = i
            idx = best_idx if best_idx is not None else remaining[0]

        selected_indices.append(idx)
        remaining.remove(idx)

    return [candidates[i] for i in selected_indices]


def _cosine_sim_batch(vec: "np.ndarray", matrix: "np.ndarray") -> "np.ndarray":  # type: ignore[name-defined]
    import numpy as np

    norm_vec = np.linalg.norm(vec)
    norm_mat = np.linalg.norm(matrix, axis=1)
    denom = norm_vec * norm_mat
    denom = np.where(denom == 0, 1e-10, denom)
    return matrix.dot(vec) / denom


def _apply_token_budget(chunks: list[dict], max_tokens: int) -> list[dict]:
    """Greedily include chunks (highest score first) until budget is exhausted."""
    total = 0
    result = []
    for chunk in chunks:
        text = chunk.get("text", "")
        # Rough token estimate: ceil(chars / 4)
        tokens = math.ceil(len(text) / 4)
        if total + tokens > max_tokens:
            break
        result.append(chunk)
        total += tokens
    return result


def _format_chunks(chunks: list[dict], kb_label: str) -> str:
    """Format retrieved chunks for context injection."""
    parts: list[str] = [f"[{kb_label}]"]
    for chunk in chunks:
        title = chunk.get("document_title", "Document")
        section = chunk.get("section_path", "")
        text = chunk.get("text", "")
        score = chunk.get("similarity", 0)
        location = f" — {section}" if section else ""
        parts.append(
            f"Source: {title}{location}\n---\n{text}\n[Relevance: {score:.3f}]"
        )
    return "\n\n".join(parts)
