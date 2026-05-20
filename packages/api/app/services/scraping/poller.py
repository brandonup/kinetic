"""
Scrape source poller job — KIN-462.

APScheduler job that runs every 5 minutes, finds due scrape sources,
runs scrapers, deduplicates posts, and feeds new content into the
existing ingestion pipeline starting from the chunking stage.

Design doc: docs/plans/2026-04-05-scheduled-kb-scraping-design.md § Scheduling + § Ingestion Flow.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLL_INTERVAL_MINUTES = 5
MAX_BACKOFF_HOURS = 24
BASE_BACKOFF_MINUTES = 5
MAX_CONSECUTIVE_FAILURES = 5

FREQUENCY_DELTAS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client():
    """Thin wrapper — importable for test patching."""
    from app.db.supabase_client import get_supabase

    return get_supabase()


def _resolve_scraper(source_type: str):
    """Get scraper instance. Thin wrapper for test patching."""
    from app.services.scraping.registry import get_scraper

    return get_scraper(source_type)


async def _dispatch_ingestion(supabase, **kwargs) -> None:
    """Dispatch ingestion from chunking stage. Thin wrapper for test patching."""
    from app.services.ingestion.pipeline import run_ingestion_from_stage

    await run_ingestion_from_stage(supabase, **kwargs)


def _calculate_next_run(frequency: str, from_time: datetime | None = None) -> datetime:
    """Calculate next_run_at based on frequency from a given time."""
    base = from_time or datetime.now(timezone.utc)
    delta = FREQUENCY_DELTAS.get(frequency, timedelta(days=1))
    return base + delta


def _calculate_backoff(consecutive_failures: int) -> timedelta:
    """Exponential backoff: 5min * 2^failures, capped at 24 hours."""
    minutes = BASE_BACKOFF_MINUTES * (2 ** consecutive_failures)
    max_minutes = MAX_BACKOFF_HOURS * 60
    return timedelta(minutes=min(minutes, max_minutes))


# ---------------------------------------------------------------------------
# Per-source processing
# ---------------------------------------------------------------------------


async def _process_source(supabase, source_row: dict) -> None:
    """Process a single due scrape source: scrape, dedup, ingest.

    Each source is independent — failures are contained and don't affect others.
    """
    source_id = source_row["id"]
    user_id = source_row["user_id"]
    kb_id = source_row["knowledge_base_id"]
    source_type = source_row["source_type"]
    frequency = source_row["frequency"]
    loop = asyncio.get_running_loop()

    try:
        # Embedding uses platform Gemini key — no user BYOK required (KIN-467)

        # Decrypt credential if present
        credential: str | None = None
        if source_row.get("credential_ciphertext") and source_row.get("credential_nonce"):
            from app.services.encryption import decrypt_api_key, load_master_key
            from app.services.user_keys import to_bytes

            master_key = load_master_key()
            ct = to_bytes(source_row["credential_ciphertext"])
            nonce = to_bytes(source_row["credential_nonce"])
            credential = decrypt_api_key(ct, nonce, master_key, user_id)

        # Build ScrapeSource model
        from app.services.scraping.base import ScrapeSource

        source = ScrapeSource(
            id=source_id,
            knowledge_base_id=kb_id,
            user_id=user_id,
            source_type=source_type,
            source_url=source_row["source_url"],
            frequency=frequency,
            credential=credential,
            is_active=source_row["is_active"],
            last_scraped_at=source_row.get("last_scraped_at"),
            next_run_at=source_row["next_run_at"],
            consecutive_failures=source_row.get("consecutive_failures", 0),
        )

        # Resolve scraper and run
        scraper = _resolve_scraper(source_type)
        posts = await scraper.scrape(source)

        # Dedup against existing posts
        existing_result = await loop.run_in_executor(
            None,
            lambda: supabase.table("scrape_source_posts")
            .select("external_id")
            .eq("scrape_source_id", source_id)
            .execute(),
        )
        existing_ids = {r["external_id"] for r in (existing_result.data or [])}
        new_posts = [p for p in posts if p.external_id not in existing_ids]

        # Resolve project_id/agent_definition_id from KB
        kb_result = await loop.run_in_executor(
            None,
            lambda: supabase.table("knowledge_bases")
            .select("project_id, agent_definition_id")
            .eq("id", kb_id)
            .single()
            .execute(),
        )
        kb_data = kb_result.data or {}
        project_id = kb_data.get("project_id")
        agent_definition_id = kb_data.get("agent_definition_id")

        # Ingest each new post
        for post in new_posts:
            await _ingest_post(
                supabase, loop,
                source_id=source_id,
                user_id=user_id,
                kb_id=kb_id,
                project_id=project_id,
                agent_definition_id=agent_definition_id,
                post=post,
            )

        # Success: update source state
        now = datetime.now(timezone.utc)
        next_run = _calculate_next_run(frequency, now)
        await loop.run_in_executor(
            None,
            lambda: supabase.table("scrape_sources")
            .update({
                "last_scraped_at": now.isoformat(),
                "next_run_at": next_run.isoformat(),
                "consecutive_failures": 0,
                "last_error": None,
            })
            .eq("id", source_id)
            .execute(),
        )
        logger.info(
            "Source %s: scraped %d posts, %d new, next run at %s",
            source_id, len(posts), len(new_posts), next_run.isoformat(),
        )

    except Exception as exc:
        logger.error("Source %s failed: %s", source_id, exc, exc_info=True)
        await _handle_source_failure(supabase, loop, source_row, exc)


async def _ingest_post(
    supabase,
    loop: asyncio.AbstractEventLoop,
    source_id: str,
    user_id: str,
    kb_id: str,
    project_id: str | None,
    agent_definition_id: str | None,
    post,
) -> None:
    """Create KB document, upload text, insert dedup row, dispatch chunking."""
    from app.core.config import settings

    document_id = uuid4()

    # Create knowledge_base_documents row
    await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents")
        .insert({
            "id": str(document_id),
            "knowledge_base_id": kb_id,
            "title": post.title or post.external_id,
            "file_type": "text/plain",
            "status": "pending",
            "retry_count": 0,
        })
        .execute(),
    )

    # Upload extracted text to Storage
    storage_path = f"{document_id}/extracted.txt"
    try:
        await loop.run_in_executor(
            None,
            lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
            .upload(storage_path, post.content.encode("utf-8"), {"content-type": "text/plain"}),
        )
    except Exception as exc:
        logger.warning("Storage upload failed for doc %s: %s (non-fatal)", document_id, exc)

    # Insert dedup row
    await loop.run_in_executor(
        None,
        lambda: supabase.table("scrape_source_posts")
        .insert({
            "scrape_source_id": source_id,
            "user_id": user_id,
            "external_id": post.external_id,
            "document_id": str(document_id),
            "url": post.url,
            "title": post.title,
        })
        .execute(),
    )

    # Dispatch ingestion from chunking stage (text already extracted)
    try:
        await _dispatch_ingestion(
            supabase,
            document_id=document_id,
            knowledge_base_id=UUID(kb_id),
            project_id=UUID(project_id) if project_id else None,
            agent_definition_id=UUID(agent_definition_id) if agent_definition_id else None,
            start_stage="chunking",
            extracted_text=post.content,
            filename=f"{post.title or post.external_id}.txt",
            content_type="text/plain",
        )
    except Exception as exc:
        logger.error("Ingestion failed for doc %s (source %s): %s", document_id, source_id, exc)
        # Mark document as failed — don't crash the poller
        await loop.run_in_executor(
            None,
            lambda: supabase.table("knowledge_base_documents")
            .update({"status": "failed", "error_message": str(exc)[:500]})
            .eq("id", str(document_id))
            .execute(),
        )


async def _handle_source_failure(
    supabase, loop: asyncio.AbstractEventLoop, source_row: dict, exc: Exception,
) -> None:
    """Update source on failure: increment failures, apply backoff, auto-deactivate."""
    source_id = source_row["id"]
    failures = source_row.get("consecutive_failures", 0) + 1
    backoff = _calculate_backoff(failures)
    next_run = datetime.now(timezone.utc) + backoff

    updates: dict = {
        "consecutive_failures": failures,
        "last_error": str(exc)[:500],
        "next_run_at": next_run.isoformat(),
    }

    if failures >= MAX_CONSECUTIVE_FAILURES:
        updates["is_active"] = False
        logger.warning(
            "Source %s auto-deactivated after %d consecutive failures",
            source_id, failures,
        )

    await loop.run_in_executor(
        None,
        lambda: supabase.table("scrape_sources")
        .update(updates)
        .eq("id", source_id)
        .execute(),
    )


# ---------------------------------------------------------------------------
# Main poller entry point
# ---------------------------------------------------------------------------


async def poll_scrape_sources() -> None:
    """APScheduler job: find due sources and process them sequentially.

    Uses service-role client. Sources are processed one at a time to
    stay within BYOK rate limits. Each source is independent — one failure
    doesn't block others.

    Note: MVP uses simple query + sequential processing. For multi-instance
    deployments, add an RPC with FOR UPDATE SKIP LOCKED to prevent
    double-processing.
    """
    try:
        supabase = _get_client()
    except Exception as exc:
        logger.error("Poller: failed to get Supabase client: %s", exc)
        return

    loop = asyncio.get_running_loop()
    now = datetime.now(timezone.utc).isoformat()

    # Find due sources
    try:
        result = await loop.run_in_executor(
            None,
            lambda: supabase.table("scrape_sources")
            .select("*")
            .eq("is_active", True)
            .lte("next_run_at", now)
            .order("next_run_at")
            .execute(),
        )
        due_sources = result.data or []
    except Exception as exc:
        logger.error("Poller: failed to query due sources: %s", exc)
        return

    if not due_sources:
        return

    logger.info("Poller: found %d due source(s)", len(due_sources))

    for source_row in due_sources:
        try:
            await _process_source(supabase, source_row)
        except Exception as exc:
            # Should never reach here (_process_source catches its own errors)
            # but guard against unexpected failures
            logger.error(
                "Poller: unhandled error processing source %s: %s",
                source_row.get("id"), exc, exc_info=True,
            )
