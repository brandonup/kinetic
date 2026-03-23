"""
Framework CRUD + bulk upload — KIN-287 (partial), KIN-289.

Schema ref: docs/db-schema-spec.md §14 (frameworks), §15 (framework_trigger_embeddings)
ADR ref:    docs/adr-003-agents-architecture.md §10 (bulk upload merge logic)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from pydantic import BaseModel, field_validator

from app.auth import CurrentUser, get_current_user
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.db import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["frameworks"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateFrameworkRequest(BaseModel):
    framework_id: str       # Semantic kebab-case ID
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    when_to_apply: list[str]
    principles: list[str]
    steps: Optional[list[str]] = None
    example_application: Optional[str] = None
    related_frameworks: Optional[list[str]] = None
    source_posts: Optional[list[dict]] = None
    confidence: str = "high"
    origin: str = "manual"

    @field_validator("when_to_apply")
    @classmethod
    def triggers_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("when_to_apply must have at least one trigger")
        return v

    @field_validator("principles")
    @classmethod
    def principles_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("principles must have at least one entry")
        return v

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, v: str) -> str:
        if v not in ("high", "medium"):
            raise ValueError("confidence must be high or medium")
        return v

    @field_validator("origin")
    @classmethod
    def valid_origin(cls, v: str) -> str:
        if v not in ("extracted", "manual"):
            raise ValueError("origin must be extracted or manual")
        return v


class UpdateFrameworkRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    when_to_apply: Optional[list[str]] = None
    principles: Optional[list[str]] = None
    steps: Optional[list[str]] = None
    example_application: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


async def _require_agent_owner(
    supabase: Any, agent_id: str, user_id: str
) -> dict:
    result = await _run(
        lambda: supabase.table("agent_definitions")
        .select("id, owner_id")
        .eq("id", agent_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise NotFoundError("Agent not found")
    if result.data["owner_id"] != user_id:
        raise ForbiddenError("Only the agent owner can manage frameworks")
    return result.data


async def _embed_triggers(
    framework_db_id: str,
    agent_definition_id: str,
    triggers: list[str],
    supabase: Any,
) -> None:
    """Embed each trigger phrase and store in framework_trigger_embeddings.

    Runs as background work after framework create/update.
    Failures are logged but do not raise — trigger missing = skipped in pipeline.
    """
    from app.services.embedding_service import embed_text

    # Delete old embeddings for this framework (for updates)
    await _run(
        lambda: supabase.table("framework_trigger_embeddings")
        .delete()
        .eq("framework_db_id", framework_db_id)
        .execute()
    )

    rows = []
    for trigger in triggers:
        try:
            embedding = await embed_text(trigger)
            rows.append(
                {
                    "framework_db_id": framework_db_id,
                    "agent_definition_id": agent_definition_id,
                    "trigger_text": trigger,
                    "embedding": embedding,
                    "embedding_model": "text-embedding-3-large",
                }
            )
        except Exception:
            logger.exception(
                "Failed to embed trigger '%s' for framework %s", trigger, framework_db_id
            )

    if rows:
        await _run(
            lambda: supabase.table("framework_trigger_embeddings")
            .insert(rows)
            .execute()
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{agent_id}/frameworks")
async def list_frameworks(
    agent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> list:
    supabase = get_supabase_client()
    aid = str(agent_id)

    # Accessible if owner or invoker (agent is public)
    agent = await _run(
        lambda: supabase.table("agent_definitions")
        .select("id, owner_id, visibility")
        .eq("id", aid)
        .maybe_single()
        .execute()
    )
    if not agent.data:
        raise NotFoundError("Agent not found")
    if (
        agent.data["owner_id"] != current_user.id
        and agent.data.get("visibility") != "public"
    ):
        raise ForbiddenError("You do not have access to this agent's frameworks")

    result = await _run(
        lambda: supabase.table("frameworks")
        .select("*")
        .eq("agent_definition_id", aid)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


@router.post("/{agent_id}/frameworks", status_code=status.HTTP_201_CREATED)
async def create_framework(
    agent_id: UUID,
    body: CreateFrameworkRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    aid = str(agent_id)
    await _require_agent_owner(supabase, aid, current_user.id)

    row = {
        "agent_definition_id": aid,
        "framework_id": body.framework_id,
        "name": body.name,
        "description": body.description,
        "category": body.category,
        "when_to_apply": body.when_to_apply,
        "principles": body.principles,
        "steps": body.steps,
        "example_application": body.example_application,
        "related_frameworks": body.related_frameworks,
        "source_posts": body.source_posts,
        "confidence": body.confidence,
        "origin": body.origin,
    }
    result = await _run(
        lambda: supabase.table("frameworks").insert(row).execute()
    )
    if not result.data:
        raise ValidationError("Failed to create framework")
    fw = result.data[0]

    # Enqueue trigger embedding as background task
    import asyncio as _asyncio

    _asyncio.ensure_future(
        _embed_triggers(fw["id"], aid, body.when_to_apply, supabase)
    )
    return fw


@router.post("/{agent_id}/frameworks/upload")
async def bulk_upload_frameworks(
    agent_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Bulk upload frameworks from a JSON file (merge behaviour per ADR-003 §10).
    Matching framework_id → update, new → add, missing → retain.
    """
    supabase = get_supabase_client()
    aid = str(agent_id)
    await _require_agent_owner(supabase, aid, current_user.id)

    try:
        content = await file.read()
        data = json.loads(content)
    except Exception:
        raise ValidationError("Invalid JSON file")

    if not isinstance(data, list):
        raise ValidationError("JSON file must contain an array of framework objects")

    # Fetch existing frameworks for merge
    existing_result = await _run(
        lambda: supabase.table("frameworks")
        .select("id, framework_id, when_to_apply")
        .eq("agent_definition_id", aid)
        .execute()
    )
    existing_map: dict[str, dict] = {
        fw["framework_id"]: fw for fw in (existing_result.data or [])
    }

    imported = 0
    updated = 0
    skipped = 0
    errors: list[dict] = []

    for item in data:
        if not isinstance(item, dict):
            errors.append({"id": None, "reason": "Item is not a JSON object"})
            skipped += 1
            continue

        fw_id = item.get("framework_id") or item.get("id")
        if not fw_id:
            errors.append({"id": None, "reason": "missing required field: framework_id"})
            skipped += 1
            continue

        # Validate required fields
        missing = [
            f
            for f in ("name", "when_to_apply", "principles")
            if not item.get(f)
        ]
        if missing:
            errors.append(
                {"id": fw_id, "reason": f"missing required fields: {', '.join(missing)}"}
            )
            skipped += 1
            continue

        if not isinstance(item.get("when_to_apply"), list) or not item["when_to_apply"]:
            errors.append({"id": fw_id, "reason": "when_to_apply must be a non-empty array"})
            skipped += 1
            continue

        row = {
            "agent_definition_id": aid,
            "framework_id": fw_id,
            "name": item["name"],
            "description": item.get("description"),
            "category": item.get("category"),
            "when_to_apply": item["when_to_apply"],
            "principles": item.get("principles", []),
            "steps": item.get("steps"),
            "example_application": item.get("example_application"),
            "related_frameworks": item.get("related_frameworks"),
            "source_posts": item.get("source_posts"),
            "confidence": item.get("confidence", "high"),
            "origin": item.get("origin", "extracted"),
        }

        try:
            if fw_id in existing_map:
                existing = existing_map[fw_id]
                await _run(
                    lambda: supabase.table("frameworks")  # noqa: B023
                    .update(row)
                    .eq("id", existing["id"])
                    .execute()
                )
                # Re-embed triggers only if when_to_apply changed
                old_triggers = set(existing.get("when_to_apply") or [])
                new_triggers = set(item["when_to_apply"])
                if old_triggers != new_triggers:
                    import asyncio as _asyncio

                    _asyncio.ensure_future(
                        _embed_triggers(
                            existing["id"], aid, item["when_to_apply"], supabase
                        )
                    )
                updated += 1
            else:
                ins = await _run(
                    lambda: supabase.table("frameworks").insert(row).execute()  # noqa: B023
                )
                if ins.data:
                    import asyncio as _asyncio

                    _asyncio.ensure_future(
                        _embed_triggers(
                            ins.data[0]["id"], aid, item["when_to_apply"], supabase
                        )
                    )
                    imported += 1
        except Exception as exc:
            errors.append({"id": fw_id, "reason": str(exc)})
            skipped += 1

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


@router.patch("/{agent_id}/frameworks/{framework_db_id}")
async def update_framework(
    agent_id: UUID,
    framework_db_id: UUID,
    body: UpdateFrameworkRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    aid = str(agent_id)
    fid = str(framework_db_id)
    await _require_agent_owner(supabase, aid, current_user.id)

    existing = await _run(
        lambda: supabase.table("frameworks")
        .select("*")
        .eq("id", fid)
        .eq("agent_definition_id", aid)
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise NotFoundError("Framework not found")

    updates: dict = {}
    re_embed = False
    for field in ("name", "description", "category", "steps", "example_application"):
        val = getattr(body, field)
        if val is not None:
            updates[field] = val
    if body.when_to_apply is not None:
        updates["when_to_apply"] = body.when_to_apply
        old = set(existing.data.get("when_to_apply") or [])
        if old != set(body.when_to_apply):
            re_embed = True
    if body.principles is not None:
        updates["principles"] = body.principles

    if not updates:
        return existing.data

    result = await _run(
        lambda: supabase.table("frameworks")
        .update(updates)
        .eq("id", fid)
        .execute()
    )
    if not result.data:
        raise NotFoundError("Framework not found")

    if re_embed:
        import asyncio as _asyncio

        _asyncio.ensure_future(
            _embed_triggers(fid, aid, body.when_to_apply, supabase)
        )
    return result.data[0]


@router.delete(
    "/{agent_id}/frameworks/{framework_db_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_framework(
    agent_id: UUID,
    framework_db_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    supabase = get_supabase_client()
    aid = str(agent_id)
    fid = str(framework_db_id)
    await _require_agent_owner(supabase, aid, current_user.id)

    existing = await _run(
        lambda: supabase.table("frameworks")
        .select("id")
        .eq("id", fid)
        .eq("agent_definition_id", aid)
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise NotFoundError("Framework not found")

    await _run(
        lambda: supabase.table("frameworks").delete().eq("id", fid).execute()
    )
