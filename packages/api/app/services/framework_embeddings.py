"""
Background job for framework trigger embedding population (ADR-007, KIN-412).
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.db.supabase_client import create_supabase
from app.services.ingestion.embedder import EmbeddingService
from app.services.user_keys import fetch_user_key

logger = logging.getLogger(__name__)


async def embed_framework_triggers(
    framework_db_id: str,
    agent_definition_id: str,
    triggers: list[str],
    user_id: str,
) -> None:
    """
    Background job: embed trigger phrases and insert into framework_trigger_embeddings.

    Fail-open: if no OpenAI key, logs warning and returns (framework is "dormant").
    Idempotent: deletes existing trigger embeddings for this framework before inserting.
    All Supabase calls via run_in_executor (sync client, async context).

    ADR-007 §2 and §3. Called by framework CRUD endpoints (create, update, bulk upload).
    """
    if not triggers:
        return

    loop = asyncio.get_running_loop()
    client = create_supabase()  # Fresh client — avoids HTTP/2 contention with the singleton

    # Fetch owner's BYOK OpenAI key
    openai_key = await loop.run_in_executor(
        None, lambda: fetch_user_key(client, user_id, "openai")
    )
    if not openai_key:
        logger.warning(
            "embed_framework_triggers: no OpenAI key for user %s — "
            "skipping trigger embedding for framework %s (dormant)",
            user_id,
            framework_db_id,
        )
        return

    # Embed all triggers (sync EmbeddingService, run in executor)
    embedder = EmbeddingService(api_key=openai_key)
    try:
        embeddings = await loop.run_in_executor(
            None, lambda: embedder.embed_batch(triggers)
        )
    except Exception:
        logger.error(
            "embed_framework_triggers: embedding failed for framework %s",
            framework_db_id,
            exc_info=True,
        )
        return

    # Delete existing trigger embeddings for this framework (idempotent)
    await loop.run_in_executor(
        None,
        lambda: client.table("framework_trigger_embeddings")
            .delete()
            .eq("framework_db_id", framework_db_id)
            .execute(),
    )

    # Build and insert fresh rows
    rows = [
        {
            "framework_db_id": framework_db_id,
            "agent_definition_id": agent_definition_id,
            "trigger_text": trigger,
            "embedding": emb,
            "embedding_model": settings.EMBEDDING_MODEL,
        }
        for trigger, emb in zip(triggers, embeddings)
    ]
    try:
        await loop.run_in_executor(
            None,
            lambda: client.table("framework_trigger_embeddings").insert(rows).execute(),
        )
        logger.info(
            "embed_framework_triggers: embedded %d triggers for framework %s",
            len(rows),
            framework_db_id,
        )
    except Exception:
        logger.error(
            "embed_framework_triggers: insert failed for framework %s",
            framework_db_id,
            exc_info=True,
        )
