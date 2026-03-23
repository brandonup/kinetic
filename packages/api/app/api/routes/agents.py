"""
AgentDefinition + AgentInstance CRUD endpoints — KIN-287, KIN-288.

AgentDefinition endpoints:
  GET    /api/v1/agents              — list owned + public agents
  POST   /api/v1/agents              — create AgentDefinition
  GET    /api/v1/agents/:id          — get single AgentDefinition
  PATCH  /api/v1/agents/:id          — update fields (owner only)
  DELETE /api/v1/agents/:id          — delete agent (owner only)
  POST   /api/v1/agents/:id/generate-instructions — stub (Sprint 5)

AgentInstance endpoints:
  GET    /api/v1/agents/:id/instance — get-or-create AgentInstance
  PATCH  /api/v1/agents/:id/instance — update framework_overrides

Spec ref: docs/specs/agents.md
ADR ref:  docs/adr-003-agents-architecture.md
Schema ref: docs/db-schema-spec.md §8–9
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

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateAgentRequest(BaseModel):
    name: str
    instructions: Optional[str] = None
    type: str = "custom"
    visibility: str = "private"
    mcp_enabled: bool = False

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("custom", "thought_leader"):
            raise ValueError("type must be 'custom' or 'thought_leader'")
        return v

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: str) -> str:
        if v not in ("private", "public"):
            raise ValueError("visibility must be 'private' or 'public'")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        if len(v) > 100:
            raise ValueError("name must be 100 characters or fewer")
        return v


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    instructions: Optional[str] = None
    visibility: Optional[str] = None
    mcp_enabled: Optional[bool] = None

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("private", "public"):
            raise ValueError("visibility must be 'private' or 'public'")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("name cannot be empty")
            if len(v) > 100:
                raise ValueError("name must be 100 characters or fewer")
        return v


class FrameworkOverrides(BaseModel):
    pinned: list[str] = []
    excluded: list[str] = []


class UpdateInstanceRequest(BaseModel):
    framework_overrides: Optional[FrameworkOverrides] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


async def _fetch_agent(supabase: Any, agent_id: str, user_id: str) -> dict:
    """
    Fetch an AgentDefinition visible to user_id (owned OR public).
    Raises NotFoundError if not found or not accessible.
    """
    result = await _run(
        lambda: supabase.table("agent_definitions")
        .select("*")
        .eq("id", agent_id)
        .execute()
    )
    rows = result.data or []
    for row in rows:
        if row["owner_id"] == user_id or row["visibility"] == "public":
            return row
    raise NotFoundError("Agent not found")


async def _require_owner(supabase: Any, agent_id: str, user_id: str) -> dict:
    """
    Fetch an AgentDefinition and assert the requesting user is the owner.
    Raises NotFoundError if agent doesn't exist, ForbiddenError if not owner.
    """
    result = await _run(
        lambda: supabase.table("agent_definitions")
        .select("*")
        .eq("id", agent_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise NotFoundError("Agent not found")
    if result.data["owner_id"] != user_id:
        raise ForbiddenError("You are not the owner of this agent")
    return result.data


async def _get_or_create_instance(
    supabase: Any,
    agent_definition_id: str,
    user_id: str,
) -> dict:
    """
    Get-or-create AgentInstance for (user_id, agent_definition_id).
    Uses ON CONFLICT DO NOTHING + re-select for race-condition safety.
    ADR ref: docs/adr-003-agents-architecture.md §2
    """
    # Fast path — existing instance
    result = await _run(
        lambda: supabase.table("agent_instances")
        .select("*")
        .eq("agent_definition_id", agent_definition_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if result.data:
        return result.data

    # Create new instance — ON CONFLICT DO NOTHING handled by DB unique constraint
    await _run(
        lambda: supabase.table("agent_instances")
        .insert({
            "agent_definition_id": agent_definition_id,
            "user_id": user_id,
            "framework_overrides": {"pinned": [], "excluded": []},
        })
        .execute()
    )

    # Re-select (our insert may have lost a concurrent race — this always returns the row)
    result = await _run(
        lambda: supabase.table("agent_instances")
        .select("*")
        .eq("agent_definition_id", agent_definition_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise ValidationError("Failed to create agent instance")
    return result.data


# ---------------------------------------------------------------------------
# AgentDefinition endpoints
# ---------------------------------------------------------------------------


@router.get("", status_code=status.HTTP_200_OK)
async def list_agents(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """
    List agents accessible to the current user:
    - All agents owned by the user (private + public)
    - All public agents owned by other users
    """
    supabase = get_supabase_client()
    user_id = current_user.user_id

    result = await _run(
        lambda: supabase.table("agent_definitions")
        .select("*")
        .execute()
    )
    rows = result.data or []
    # Filter: owned by user OR public (DB RLS enforces this in prod;
    # we also filter in application layer for defense-in-depth)
    return [
        r for r in rows
        if r["owner_id"] == user_id or r["visibility"] == "public"
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: CreateAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Create a new AgentDefinition owned by the current user."""
    if body.visibility == "public" and not (body.instructions or "").strip():
        raise ValidationError("instructions must be non-empty to set visibility to 'public'")

    supabase = get_supabase_client()
    user_id = current_user.user_id

    row = {
        "owner_id": user_id,
        "name": body.name,
        "type": body.type,
        "visibility": body.visibility,
        "mcp_enabled": body.mcp_enabled,
    }
    if body.instructions is not None:
        row["instructions"] = body.instructions

    result = await _run(
        lambda: supabase.table("agent_definitions").insert(row).execute()
    )
    if not result.data:
        raise ValidationError("Failed to create agent")
    return result.data[0]


@router.get("/{agent_id}", status_code=status.HTTP_200_OK)
async def get_agent(
    agent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Get a single AgentDefinition (owner or any user if public)."""
    supabase = get_supabase_client()
    return await _fetch_agent(supabase, str(agent_id), current_user.user_id)


@router.patch("/{agent_id}", status_code=status.HTTP_200_OK)
async def update_agent(
    agent_id: UUID,
    body: UpdateAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Update an AgentDefinition (owner only)."""
    supabase = get_supabase_client()
    agent = await _require_owner(supabase, str(agent_id), current_user.user_id)

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.instructions is not None:
        updates["instructions"] = body.instructions
    if body.visibility is not None:
        # Guard: cannot set public without instructions
        effective_instructions = body.instructions or agent.get("instructions") or ""
        if body.visibility == "public" and not effective_instructions.strip():
            raise ValidationError("instructions must be non-empty to set visibility to 'public'")
        updates["visibility"] = body.visibility
    if body.mcp_enabled is not None:
        updates["mcp_enabled"] = body.mcp_enabled

    if not updates:
        return agent

    updates["updated_at"] = datetime.datetime.utcnow().isoformat()
    result = await _run(
        lambda: supabase.table("agent_definitions")
        .update(updates)
        .eq("id", str(agent_id))
        .execute()
    )
    if not result.data:
        raise ValidationError("Failed to update agent")
    return result.data[0]


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """
    Delete an AgentDefinition (owner only).
    Blocked if agent is public and has active invokers (AgentInstances from other users).
    """
    supabase = get_supabase_client()
    agent = await _require_owner(supabase, str(agent_id), current_user.user_id)

    # Block delete if public and has invokers (non-owner instances)
    if agent["visibility"] == "public":
        instances_result = await _run(
            lambda: supabase.table("agent_instances")
            .select("id", count="exact")
            .eq("agent_definition_id", str(agent_id))
            .neq("user_id", current_user.user_id)
            .execute()
        )
        invoker_count = instances_result.count or 0
        if invoker_count > 0:
            raise ValidationError(
                "Cannot delete a public agent that has active invokers. "
                "Set visibility to 'private' first or transfer ownership."
            )

    await _run(
        lambda: supabase.table("agent_definitions")
        .delete()
        .eq("id", str(agent_id))
        .execute()
    )


@router.post("/{agent_id}/generate-instructions", status_code=status.HTTP_200_OK)
async def generate_instructions(
    agent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Auto-generate a system prompt from the agent's KB.
    Stub — full implementation deferred to Sprint 5.
    ADR ref: docs/adr-003-agents-architecture.md §9
    """
    supabase = get_supabase_client()
    await _require_owner(supabase, str(agent_id), current_user.user_id)
    # TODO Sprint 5: fetch KB content, call BYOK LLM, return draft instructions
    return {"instructions": "", "status": "stub — not yet implemented"}


# ---------------------------------------------------------------------------
# AgentInstance endpoints (KIN-288)
# ---------------------------------------------------------------------------


@router.get("/{agent_id}/instance", status_code=status.HTTP_200_OK)
async def get_instance(
    agent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Get (or create) the AgentInstance for the current user + this AgentDefinition.
    Auto-creates on first invocation — get-or-create pattern.
    ADR ref: docs/adr-003-agents-architecture.md §2
    """
    supabase = get_supabase_client()
    user_id = current_user.user_id
    agent_id_str = str(agent_id)

    # Verify the agent is accessible (owned or public)
    await _fetch_agent(supabase, agent_id_str, user_id)

    return await _get_or_create_instance(supabase, agent_id_str, user_id)


@router.patch("/{agent_id}/instance", status_code=status.HTTP_200_OK)
async def update_instance(
    agent_id: UUID,
    body: UpdateInstanceRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update the current user's AgentInstance for this agent.
    Supports: framework_overrides (pinned/excluded).
    Active memory updates are handled via the active_memory_entries endpoint (Sprint 5).
    """
    supabase = get_supabase_client()
    user_id = current_user.user_id
    agent_id_str = str(agent_id)

    # Verify agent is accessible
    await _fetch_agent(supabase, agent_id_str, user_id)

    # Get or create instance
    instance = await _get_or_create_instance(supabase, agent_id_str, user_id)

    updates: dict = {}
    if body.framework_overrides is not None:
        updates["framework_overrides"] = body.framework_overrides.model_dump()

    if not updates:
        return instance

    updates["updated_at"] = datetime.datetime.utcnow().isoformat()
    result = await _run(
        lambda: supabase.table("agent_instances")
        .update(updates)
        .eq("id", instance["id"])
        .execute()
    )
    if not result.data:
        raise ValidationError("Failed to update agent instance")
    return result.data[0]
