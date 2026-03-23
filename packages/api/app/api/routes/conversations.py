"""
Conversation CRUD endpoints — KIN-272.

Implements POST, GET (list), GET (detail), PATCH, DELETE for conversations.
The POST /messages (generation + SSE streaming) is Big Head's endpoint (KIN-276).

Schema ref: docs/db-schema-spec.md §5 (conversations), §6 (messages)
Spec ref:   docs/specs/kin-257-projects-conversations-spec.md §2.2
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator

from app.auth import CurrentUser, get_current_user
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.db import get_supabase_client

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CreateConversationRequest(BaseModel):
    company_id: UUID
    project_id: Optional[UUID] = None
    title: Optional[str] = None


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    active_agent_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro: Any) -> Any:
    """Run a sync supabase call in the default thread pool."""
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, coro)


async def _verify_company_ownership(
    supabase: Any,
    company_id: str,
    user_id: str,
) -> None:
    """Raise ForbiddenError if company_id does not belong to user_id."""
    result = await _run(
        lambda: supabase.table("companies")
        .select("id")
        .eq("id", company_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise ForbiddenError("Company not found or does not belong to you")


async def _verify_project_ownership(
    supabase: Any,
    project_id: str,
    company_id: str,
    user_id: str,
) -> None:
    """Raise 404/403 if project_id is not owned by user or does not belong to company."""
    result = await _run(
        lambda: supabase.table("projects")
        .select("id")
        .eq("id", project_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise NotFoundError("Project not found")
    result2 = await _run(
        lambda: supabase.table("projects")
        .select("id")
        .eq("id", project_id)
        .eq("company_id", company_id)
        .maybe_single()
        .execute()
    )
    if not result2.data:
        raise ForbiddenError("Project does not belong to the specified company")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: CreateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    company_id = str(body.company_id)
    project_id = str(body.project_id) if body.project_id else None
    user_id = current_user.user_id

    await _verify_company_ownership(supabase, company_id, user_id)
    if project_id:
        await _verify_project_ownership(supabase, project_id, company_id, user_id)

    row: dict = {
        "user_id": user_id,
        "company_id": company_id,
        "project_id": project_id,
        "title": body.title,
        "active_agent_id": None,
    }

    result = await _run(
        lambda: supabase.table("conversations").insert(row).execute()
    )
    if not result.data:
        raise ValidationError("Failed to create conversation")
    return result.data[0]


@router.get("")
async def list_conversations(
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    include_deleted: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    user_id = current_user.user_id

    if company_id:
        await _verify_company_ownership(supabase, company_id, user_id)
    if project_id:
        result_proj = await _run(
            lambda: supabase.table("projects")
            .select("id")
            .eq("id", project_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not result_proj.data:
            raise ForbiddenError("Project not found or does not belong to you")

    query = (
        supabase.table("conversations")
        .select(
            "id, company_id, project_id, title, active_agent_id, created_at, updated_at"
        )
        .eq("user_id", user_id)
    )
    if company_id:
        query = query.eq("company_id", company_id)
    if project_id:
        query = query.eq("project_id", project_id)
    if not include_deleted:
        query = query.is_("deleted_at", "null")
    query = query.order("updated_at", desc=True)

    result = await _run(lambda: query.execute())
    return {"conversations": result.data or []}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    user_id = current_user.user_id
    conv_id = str(conversation_id)

    result = await _run(
        lambda: supabase.table("conversations")
        .select(
            "id, company_id, project_id, title, active_agent_id, created_at, updated_at"
        )
        .eq("id", conv_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise NotFoundError("Conversation not found")

    # Fetch messages (exclude system role per spec §2.2)
    msg_result = await _run(
        lambda: supabase.table("messages")
        .select(
            "id, role, content, agent_definition_id, model, sequence, created_at"
        )
        .eq("conversation_id", conv_id)
        .neq("role", "system")
        .order("sequence", desc=False)
        .execute()
    )

    conversation = result.data
    conversation["messages"] = msg_result.data or []
    return conversation


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: UUID,
    body: UpdateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    user_id = current_user.user_id
    conv_id = str(conversation_id)

    # Verify ownership
    existing = await _run(
        lambda: supabase.table("conversations")
        .select("id")
        .eq("id", conv_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise NotFoundError("Conversation not found")

    updates: dict = {"updated_at": datetime.datetime.utcnow().isoformat()}

    if body.title is not None:
        updates["title"] = body.title

    # active_agent_id: None means "set to null" (deactivate), only verify if a new UUID
    if "active_agent_id" in body.model_fields_set:
        if body.active_agent_id is not None:
            agent_id = str(body.active_agent_id)
            agent_result = await _run(
                lambda: supabase.table("agent_definitions")
                .select("id, visibility, owner_id")
                .eq("id", agent_id)
                .maybe_single()
                .execute()
            )
            if not agent_result.data:
                raise NotFoundError("Agent not found")
            agent = agent_result.data
            if (
                agent["visibility"] != "public"
                and agent["owner_id"] != user_id
            ):
                raise ForbiddenError("You do not have access to this agent")
            updates["active_agent_id"] = agent_id
        else:
            updates["active_agent_id"] = None

    result = await _run(
        lambda: supabase.table("conversations")
        .update(updates)
        .eq("id", conv_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise NotFoundError("Conversation not found")
    return result.data[0]


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    supabase = get_supabase_client()
    user_id = current_user.user_id
    conv_id = str(conversation_id)

    existing = await _run(
        lambda: supabase.table("conversations")
        .select("id")
        .eq("id", conv_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise NotFoundError("Conversation not found")

    await _run(
        lambda: supabase.table("conversations")
        .update({"deleted_at": datetime.datetime.utcnow().isoformat()})
        .eq("id", conv_id)
        .eq("user_id", user_id)
        .execute()
    )
