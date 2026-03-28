"""
Thin background task abstraction.

MVP: delegates to FastAPI BackgroundTasks.
Migration to Celery/RQ: replace TaskDispatcher.dispatch() body only — no other changes needed.

ADR-001: Background processing uses FastAPI BackgroundTasks for MVP.
Gilfoyle requirement: thin abstraction layer so Celery migration is a one-file change.

Background Job Types and Retry Policy (KIN-338)
================================================

| Job Type              | Trigger                            | Retry    | Dedup                                      | Error Behavior       |
|-----------------------|------------------------------------|----------|--------------------------------------------|-----------------------|
| Document ingestion    | POST /documents/upload             | 3x, 60/300/900s backoff per stage | Atomic status check on retry endpoint | status=failed, error persisted |
| Ingestion retry       | POST /documents/{id}/retry         | Same as ingestion | Atomic WHERE status='failed' prevents concurrent retries | 409 if already retrying |
| Memory proposals      | POST /conversations/{id}/end       | None (non-fatal) | Content-level dedup against pending proposals | Silent skip, logged   |
| Periodic proposals    | POST /conversations/{id}/messages  | None (non-fatal) | Skip if pending proposals exist             | Silent skip, logged   |
| Stale job cleanup     | App startup (lifespan event)       | N/A      | N/A                                        | Marks stuck docs as failed |

Notes:
- Memory proposals use silent-skip by design: BYOK key failures should not block the API.
- Ingestion retry dedup uses atomic UPDATE WHERE status='failed' — concurrent retries get 409.
- Stale job cleanup runs once at startup, marks docs stuck in processing >30 min as failed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)

# Documents stuck in a processing state for longer than this are marked failed
STALE_JOB_TIMEOUT_MINUTES = 30


async def cleanup_stale_jobs(supabase) -> int:
    """
    Mark documents stuck in processing states as failed (KIN-338).

    Runs at app startup. Documents with status in
    ('pending', 'extracting', 'chunking', 'embedding') and updated_at older
    than STALE_JOB_TIMEOUT_MINUTES are marked failed with a stale-job error.

    Returns the number of documents cleaned up.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_JOB_TIMEOUT_MINUTES)
    cutoff_iso = cutoff.isoformat()
    loop = asyncio.get_running_loop()

    processing_states = ("pending", "extracting", "chunking", "embedding")
    cleaned = 0

    for status in processing_states:
        try:
            stale_message = f"Stale job timeout: stuck in '{status}' for >{STALE_JOB_TIMEOUT_MINUTES} minutes"

            # Docs with no existing error_message: write all three fields
            r_new = await loop.run_in_executor(
                None,
                lambda s=status, msg=stale_message: supabase.table("knowledge_base_documents")
                .update({"status": "failed", "error_stage": s, "error_message": msg})
                .eq("status", s)
                .lt("updated_at", cutoff_iso)
                .is_("deleted_at", "null")
                .is_("error_message", "null")
                .execute(),
            )
            # Docs that already have an error_message: preserve it, still mark failed
            r_preserve = await loop.run_in_executor(
                None,
                lambda s=status: supabase.table("knowledge_base_documents")
                .update({"status": "failed", "error_stage": s})
                .eq("status", s)
                .lt("updated_at", cutoff_iso)
                .is_("deleted_at", "null")
                .not_.is_("error_message", "null")
                .execute(),
            )
            count = (len(r_new.data) if r_new.data else 0) + (len(r_preserve.data) if r_preserve.data else 0)
            if count > 0:
                logger.info("Cleaned up %d stale documents in '%s' state", count, status)
                cleaned += count
        except Exception as exc:
            logger.error("Stale job cleanup failed for status '%s': %s", status, exc)

    if cleaned > 0:
        logger.info("Total stale documents cleaned up: %d", cleaned)
    return cleaned


class TaskDispatcher:
    """
    Enqueue background tasks via FastAPI BackgroundTasks.

    Usage:
        dispatcher = TaskDispatcher(background_tasks)
        dispatcher.dispatch(my_async_fn, arg1, arg2, kwarg=value)
    """

    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._bt = background_tasks

    def dispatch(self, fn, *args, **kwargs) -> None:
        """
        Enqueue fn(*args, **kwargs) for background execution.

        MVP: delegates to BackgroundTasks.add_task.
        Celery migration: replace with celery_app.send_task(fn, args, kwargs).
        """
        self._bt.add_task(fn, *args, **kwargs)
