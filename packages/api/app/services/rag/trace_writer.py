"""
Retrieval trace writer — KIN-326.

Writes a retrieval_debug_logs row for a completed RAG retrieval pipeline run.
Designed to be called via BackgroundTasks.add_task (sync function, runs in thread pool).

Usage in the generation route (when implemented):
    from app.services.rag.trace_writer import write_retrieval_trace
    from app.services.background import TaskDispatcher

    dispatcher = TaskDispatcher(background_tasks)
    dispatcher.dispatch(
        write_retrieval_trace,
        message_id=message_id,
        scope=scope.value,
        query_text=query_text,
        vector_candidates=[{"chunk_id": c.chunk_id, "score": c.similarity_score} for c in candidates],
        mmr_selections=[...],
        injected_chunks=[{"chunk_id": c.chunk_id, "score": c.similarity_score, "text_preview": c.text[:200]} for c in injected],
        gating_decision="injected",
        supabase=get_supabase(),
    )

Failure isolation: DB errors are caught and logged. The write never raises or fails the caller.

Schema ref: docs/db-schema-spec.md §20 (retrieval_debug_logs)
Spec ref:   docs/specs/rag-debug-tab-spec.md §5
ADR ref:    reviews/2026-03-23-kin332-arch-review.md §1
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def write_retrieval_trace(
    message_id: str,
    scope: str,
    query_text: str,
    vector_candidates: list,
    mmr_selections: list,
    injected_chunks: list,
    gating_decision: str,
    supabase,
    *,
    error_message: Optional[str] = None,
    retrieval_duration_ms: Optional[int] = None,
    timings: Optional[dict] = None,
) -> None:
    """
    Write a retrieval debug trace row to retrieval_debug_logs.

    Sync function — call via BackgroundTasks.add_task or TaskDispatcher.dispatch.
    Supabase client must be service-role (bypasses RLS for INSERT).

    Args:
        message_id: FK to the conversation message that triggered retrieval.
        scope: 'project_kb' or 'agent_kb'.
        query_text: The user's original query string.
        vector_candidates: Pre-MMR candidates [{chunk_id, score}].
        mmr_selections: Post-MMR selections [{chunk_id, score}].
        injected_chunks: Final injected chunks [{chunk_id, score, text_preview}].
        gating_decision: 'injected', 'below_threshold', or 'error'.
        supabase: Sync Supabase service-role client.
        error_message: Populated on embedding failure; null for successful retrievals.
        retrieval_duration_ms: Total wall-clock ms for the retrieve() call.
        timings: Per-stage timing data {"stage_name": [start_ms, end_ms], ...}.

    Returns:
        None. Errors are logged and swallowed — this function never raises.
    """
    row = {
        "message_id": message_id,
        "scope": scope,
        "query_text": query_text,
        "vector_candidates": vector_candidates,
        "mmr_selections": mmr_selections,
        "injected_chunks": injected_chunks,
        "gating_decision": gating_decision,
        "error_message": error_message,
    }
    if retrieval_duration_ms is not None:
        row["retrieval_duration_ms"] = retrieval_duration_ms
    if timings is not None:
        row["timings"] = timings

    try:
        supabase.table("retrieval_debug_logs").insert(row).execute()
    except Exception as exc:
        # Per spec §5: if trace write fails, log server-side and continue.
        # Never fail a user query because the debug log couldn't be written.
        logger.error(
            "write_retrieval_trace: failed to write trace for message_id=%s: %s",
            message_id,
            exc,
        )
