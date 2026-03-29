"""
Admin backfill endpoint for trigger embeddings (ADR-007 §1, KIN-413).

Endpoints:
  POST /api/v1/admin/backfill-trigger-embeddings — admin-only endpoint to retroactively
    populate trigger embeddings for existing frameworks.

Admin auth guard via require_admin dependency (HTTP 403 if non-admin).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth.deps import CurrentUser, require_admin
from app.core.config import settings
from app.db.supabase_client import get_supabase
from app.services.ingestion.embedder import EmbeddingService
from app.services.user_keys import fetch_user_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin-backfill"])


def get_supabase_client():
    """Return the service-role Supabase client. Defined at module level so tests can patch it."""
    return get_supabase()


@router.post("/backfill-trigger-embeddings")
async def backfill_trigger_embeddings(
    agent_definition_id: Optional[str] = Query(
        None,
        description="Scope to a single agent definition. Omit to process all agents.",
    ),
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    Retroactively populate trigger embeddings for existing frameworks (admin only).

    - Iterates all agent definitions (or just one if agent_definition_id is provided).
    - For each agent: fetches owner's BYOK OpenAI key, embeds when_to_apply triggers,
      and inserts into framework_trigger_embeddings.
    - Skips agents whose owner has no OpenAI key (logged and counted).
    - Idempotent: deletes existing trigger embeddings per framework before inserting.

    Returns:
        {
            "processed": int,        # agents examined
            "skipped_no_key": int,   # agents skipped due to missing OpenAI key
            "frameworks_embedded": int,
            "triggers_embedded": int,
        }

    ADR-007 §1.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Step 1: Fetch agent definitions to process
    if agent_definition_id:
        agents_result = await loop.run_in_executor(
            None,
            lambda: client
                .table("agent_definitions")
                .select("id, owner_id")
                .eq("id", agent_definition_id)
                .execute(),
        )
    else:
        agents_result = await loop.run_in_executor(
            None,
            lambda: client
                .table("agent_definitions")
                .select("id, owner_id")
                .execute(),
        )

    agents = agents_result.data or []

    processed = 0
    skipped_no_key = 0
    frameworks_embedded = 0
    triggers_embedded = 0

    for agent in agents:
        aid = agent["id"]
        owner_id = agent["owner_id"]
        processed += 1

        # Step 2: Fetch owner's BYOK OpenAI key
        openai_key = await loop.run_in_executor(
            None, lambda uid=owner_id: fetch_user_key(client, uid, "openai")
        )
        if not openai_key:
            logger.warning(
                "backfill_trigger_embeddings: no OpenAI key for owner %s (agent %s) — skipping",
                owner_id,
                aid,
            )
            skipped_no_key += 1
            continue

        # Step 3: Fetch frameworks for this agent
        fw_result = await loop.run_in_executor(
            None,
            lambda a=aid: client
                .table("frameworks")
                .select("id, when_to_apply")
                .eq("agent_definition_id", a)
                .execute(),
        )
        frameworks = fw_result.data or []

        embedder = EmbeddingService(api_key=openai_key)

        for fw in frameworks:
            triggers: list[str] = fw.get("when_to_apply") or []
            if not triggers:
                continue

            fw_db_id = fw["id"]

            # Embed triggers
            try:
                embeddings = await loop.run_in_executor(
                    None, lambda t=triggers: embedder.embed_batch(t)
                )
            except Exception:
                logger.error(
                    "backfill_trigger_embeddings: embedding failed for framework %s",
                    fw_db_id,
                    exc_info=True,
                )
                continue

            # Delete existing (idempotent)
            await loop.run_in_executor(
                None,
                lambda fid=fw_db_id: client.table("framework_trigger_embeddings")
                    .delete()
                    .eq("framework_db_id", fid)
                    .execute(),
            )

            # Insert fresh rows
            rows = [
                {
                    "framework_db_id": fw_db_id,
                    "agent_definition_id": aid,
                    "trigger_text": trigger,
                    "embedding": emb,
                    "embedding_model": settings.EMBEDDING_MODEL,
                }
                for trigger, emb in zip(triggers, embeddings)
            ]
            try:
                await loop.run_in_executor(
                    None,
                    lambda r=rows: client.table("framework_trigger_embeddings").insert(r).execute(),
                )
                frameworks_embedded += 1
                triggers_embedded += len(rows)
            except Exception:
                logger.error(
                    "backfill_trigger_embeddings: insert failed for framework %s",
                    fw_db_id,
                    exc_info=True,
                )

    return {
        "processed": processed,
        "skipped_no_key": skipped_no_key,
        "frameworks_embedded": frameworks_embedded,
        "triggers_embedded": triggers_embedded,
    }
