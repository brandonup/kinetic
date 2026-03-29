"""
Admin RAG Debug API routes — KIN-326.

Endpoints:
  GET /api/v1/admin/rag-debug              — paginated list of retrieval traces (admin only)
  GET /api/v1/admin/rag-debug/{trace_id}   — full trace detail with chunk metadata join (admin only)

Both endpoints require role='admin' via require_admin dependency (HTTP 403 if non-admin).
Trace writes are NOT handled here — see app.services.rag.trace_writer.

Schema ref: docs/db-schema-spec.md §20 (retrieval_debug_logs)
Spec ref:   docs/specs/rag-debug-tab-spec.md §2-4
ADR ref:    reviews/2026-03-23-kin332-arch-review.md
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from app.auth.deps import CurrentUser, require_admin
from app.core.errors import NotFoundError
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/rag-debug", tags=["admin-rag-debug"])


# ---------------------------------------------------------------------------
# Module-level accessor — allows tests to patch the supabase client
# ---------------------------------------------------------------------------


def get_supabase_client():
    """Return the service-role Supabase client. Defined at module level so tests can patch it."""
    return get_supabase()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
async def list_rag_debug_traces(
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(None, description="created_at ISO timestamp of last item on previous page"),
    scope: Optional[Literal["project_kb", "agent_kb"]] = Query(None, description="Filter by 'project_kb' or 'agent_kb'"),
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    List recent retrieval traces (admin only).

    Paginates by created_at DESC using cursor-based pagination.
    Pass the returned next_cursor as the cursor param to fetch the next page.

    Response fields per trace:
      id, message_id, scope, query_text, gating_decision, created_at,
      injected_chunk_count (computed), vector_candidate_count (computed)

    Raises:
        AuthorizationError (403): Non-admin caller.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    try:
        result = await loop.run_in_executor(
            None,
            lambda: _list_traces_sync(client, limit, cursor, scope),
        )
    except Exception as exc:
        logger.error("list_rag_debug_traces: Supabase query failed: %s", exc)
        raise

    rows = result.data or []

    # Compute count fields from JSONB arrays + strip raw JSONB from list response
    traces = []
    for row in rows:
        traces.append({
            "id": row["id"],
            "message_id": row["message_id"],
            "scope": row["scope"],
            "query_text": row["query_text"],
            "gating_decision": row["gating_decision"],
            "retrieval_duration_ms": row.get("retrieval_duration_ms"),
            "created_at": row["created_at"],
            "injected_chunk_count": len(row.get("injected_chunks") or []),
            "vector_candidate_count": len(row.get("vector_candidates") or []),
        })

    # next_cursor is the created_at of the last item when a full page is returned
    next_cursor = traces[-1]["created_at"] if len(traces) == limit else None

    return {"traces": traces, "next_cursor": next_cursor}


def _list_traces_sync(client, limit: int, cursor: Optional[str], scope: Optional[str]):
    """
    Synchronous Supabase query for the trace list.

    Separated for run_in_executor and test legibility.
    """
    query = (
        client
        .table("retrieval_debug_logs")
        .select("id, message_id, scope, query_text, gating_decision, retrieval_duration_ms, injected_chunks, vector_candidates, created_at")
        .order("created_at", desc=True)
    )
    if scope:
        query = query.eq("scope", scope)
    if cursor:
        query = query.lt("created_at", cursor)
    return query.limit(limit).execute()


@router.get("/{trace_id}")
async def get_rag_debug_trace(
    trace_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    Return full trace detail for a single retrieval trace (admin only).

    Enriches injected_chunks with document_title and section_path via a
    join-at-read pattern (Gilfoyle Option B — see reviews/2026-03-23-kin332-arch-review.md §5).

    Raises:
        NotFoundError (404): Trace not found.
        AuthorizationError (403): Non-admin caller.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Fetch full trace row
    try:
        trace_result = await loop.run_in_executor(
            None,
            lambda: client
                .table("retrieval_debug_logs")
                .select("*")
                .eq("id", trace_id)
                .single()
                .execute(),
        )
    except Exception as exc:
        logger.error("get_rag_debug_trace: failed to fetch trace %s: %s", trace_id, exc)
        raise

    if not trace_result.data:
        raise NotFoundError("Trace not found")

    trace = dict(trace_result.data)

    # Enrich injected_chunks with document metadata (join-at-read, Option B)
    injected_chunks = trace.get("injected_chunks") or []
    if injected_chunks:
        chunk_ids = [c["chunk_id"] for c in injected_chunks if c.get("chunk_id")]
        if chunk_ids:
            try:
                chunks_result = await loop.run_in_executor(
                    None,
                    lambda: client
                        .table("knowledge_base_chunks")
                        .select("id, section_path, document_id, knowledge_base_documents(title)")
                        .in_("id", chunk_ids)
                        .execute(),
                )
            except Exception as exc:
                logger.error("get_rag_debug_trace: failed to fetch chunk metadata for trace %s: %s", trace_id, exc)
                raise
            chunk_meta: dict[str, dict] = {}
            for row in (chunks_result.data or []):
                doc = row.get("knowledge_base_documents") or {}
                if isinstance(doc, list):
                    doc = doc[0] if doc else {}
                chunk_meta[row["id"]] = {
                    "document_title": doc.get("title"),
                    "section_path": row.get("section_path"),
                }

            # Merge metadata back into injected_chunks
            enriched = []
            for chunk in injected_chunks:
                meta = chunk_meta.get(chunk.get("chunk_id"), {})
                enriched.append({**chunk, **meta})
            trace["injected_chunks"] = enriched

    return trace
