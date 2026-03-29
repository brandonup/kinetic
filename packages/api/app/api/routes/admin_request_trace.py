"""
Admin Request Trace API routes — pipeline observability.

Endpoints:
  GET /api/v1/admin/request-trace              — paginated trace list with timing (admin only)
  GET /api/v1/admin/request-trace/{trace_id}   — full trace detail with waterfall timing (admin only)

Both endpoints require role='admin' via require_admin dependency (HTTP 403 if non-admin).

Schema ref: docs/db-schema-spec.md §20 (retrieval_debug_logs)
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

router = APIRouter(prefix="/api/v1/admin/request-trace", tags=["admin-request-trace"])


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
async def list_request_traces(
    limit: int = Query(25, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="created_at ISO timestamp of last item on previous page"),
    scope: Optional[Literal["project_kb", "agent_kb"]] = Query(None, description="Filter by scope"),
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    List recent retrieval traces with timing data (admin only).

    Returns traces ordered by created_at DESC with cursor-based pagination.
    Each trace includes retrieval_duration_ms for the sidebar duration badge.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    try:
        result = await loop.run_in_executor(
            None,
            lambda: _list_traces_sync(client, limit, cursor, scope),
        )
    except Exception as exc:
        logger.error("list_request_traces: Supabase query failed: %s", exc)
        raise

    rows = result.data or []

    traces = []
    for row in rows:
        traces.append({
            "id": row["id"],
            "message_id": row["message_id"],
            "scope": row["scope"],
            "query_text": row["query_text"],
            "gating_decision": row["gating_decision"],
            "retrieval_duration_ms": row.get("retrieval_duration_ms"),
            "injected_chunk_count": len(row.get("injected_chunks") or []),
            "vector_candidate_count": len(row.get("vector_candidates") or []),
            "created_at": row["created_at"],
        })

    next_cursor = traces[-1]["created_at"] if len(traces) == limit else None

    return {"traces": traces, "next_cursor": next_cursor}


def _list_traces_sync(client, limit: int, cursor: Optional[str], scope: Optional[str]):
    """Synchronous Supabase query for the trace list."""
    query = (
        client
        .table("retrieval_debug_logs")
        .select(
            "id, message_id, scope, query_text, gating_decision, "
            "retrieval_duration_ms, injected_chunks, vector_candidates, created_at"
        )
        .order("created_at", desc=True)
    )
    if scope:
        query = query.eq("scope", scope)
    if cursor:
        query = query.lt("created_at", cursor)
    return query.limit(limit).execute()


@router.get("/{trace_id}")
async def get_request_trace(
    trace_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    Return full trace detail with waterfall timing data (admin only).

    Includes timings dict for the waterfall chart and a computed
    pipeline_stages array for easier frontend rendering.

    Enriches injected_chunks with document_title and section_path via
    join-at-read pattern.
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
        logger.error("get_request_trace: failed to fetch trace %s: %s", trace_id, exc)
        raise

    if not trace_result.data:
        raise NotFoundError("Trace not found")

    trace = dict(trace_result.data)

    # Compute pipeline_stages from timings for waterfall rendering
    timings = trace.get("timings") or {}
    pipeline_stages = []
    for stage_name, times in timings.items():
        if isinstance(times, list) and len(times) == 2:
            pipeline_stages.append({
                "name": stage_name,
                "start_ms": times[0],
                "end_ms": times[1],
                "duration_ms": round(times[1] - times[0], 2),
            })
    # Sort by start time for consistent waterfall order
    pipeline_stages.sort(key=lambda s: s["start_ms"])
    trace["pipeline_stages"] = pipeline_stages

    # Enrich injected_chunks with document metadata (join-at-read)
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
                logger.error(
                    "get_request_trace: failed to fetch chunk metadata for trace %s: %s",
                    trace_id, exc,
                )
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

            enriched = []
            for chunk in injected_chunks:
                meta = chunk_meta.get(chunk.get("chunk_id"), {})
                enriched.append({**chunk, **meta})
            trace["injected_chunks"] = enriched

    return trace
