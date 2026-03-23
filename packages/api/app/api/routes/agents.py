"""
AgentDefinition + AgentInstance CRUD — KIN-287, KIN-288.

Schema ref: docs/db-schema-spec.md §8 (agent_definitions), §9 (agent_instances)
Spec ref:   docs/specs/agents.md
ADR ref:    docs/adr-003-agents-architecture.md
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator

from app.auth import CurrentUser, get_current_user
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError, PaymentRequiredError
from app.db import get_supabase_client

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateAgentRequest(BaseModel):
    name: str
    instructions: str = ""
    type: str = "custom"
    visibility: str = "private"
    mcp_enabled: bool = False

    @field_validator("type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in ("custom", "thought_leader"):
            raise ValueError("type must be custom or thought_leader")
        return v

    @field_validator("visibility")
    @classmethod
    def valid_visibility(cls, v: str) -> str:
        if v not in ("private", "public"):
            raise ValueError("visibility must be private or public")
        return v


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    instructions: Optional[str] = None
    visibility: Optional[str] = None
    mcp_enabled: Optional[bool] = None

    @field_validator("visibility")
    @classmethod
    def valid_visibility(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("private", "public"):
            raise ValueError("visibility must be private or public")
        return v


class UpdateInstanceRequest(BaseModel):
    framework_overrides: Optional[dict] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


async def _get_agent(supabase: Any, agent_id: str, user_id: str) -> dict:
    """Get agent; accessible if owner OR public."""
    result = await _run(
        lambda: supabase.table("agent_definitions")
        .select("*")
        .eq("id", agent_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise NotFoundError("Agent not found")
    agent = result.data
    if agent["owner_id"] != user_id and agent.get("visibility") != "public":
        raise ForbiddenError("You do not have access to this agent")
    return agent


async def _require_owner(supabase: Any, agent_id: str, user_id: str) -> dict:
    """Get agent; only accessible if owner."""
    result = await _run(
        lambda: supabase.table("agent_definitions")
        .select("*")
        .eq("id", agent_id)
        .eq("owner_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise ForbiddenError("Agent not found or you are not the owner")
    return result.data


# ---------------------------------------------------------------------------
# AgentDefinition endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_agents(
    current_user: CurrentUser = Depends(get_current_user),
) -> list:
    """Return owned agents + all public agents."""
    supabase = get_supabase_client()

    # Owned
    owned = await _run(
        lambda: supabase.table("agent_definitions")
        .select("*")
        .eq("owner_id", current_user.id)
        .order("created_at", desc=True)
        .execute()
    )
    # Public (excluding own)
    public = await _run(
        lambda: supabase.table("agent_definitions")
        .select("*")
        .eq("visibility", "public")
        .neq("owner_id", current_user.id)
        .order("created_at", desc=True)
        .execute()
    )

    seen: set = set()
    results = []
    for row in (owned.data or []) + (public.data or []):
        if row["id"] not in seen:
            seen.add(row["id"])
            results.append(row)
    return results


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: CreateAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()

    if body.visibility == "public" and not body.instructions.strip():
        raise ValidationError("instructions must not be empty for public agents")

    # Name unique per owner
    existing = await _run(
        lambda: supabase.table("agent_definitions")
        .select("id")
        .eq("owner_id", current_user.id)
        .eq("name", body.name)
        .maybe_single()
        .execute()
    )
    if existing.data:
        raise ConflictError(f"An agent named '{body.name}' already exists")

    row = {
        "owner_id": current_user.id,
        "name": body.name,
        "instructions": body.instructions,
        "type": body.type,
        "visibility": body.visibility,
    }
    result = await _run(
        lambda: supabase.table("agent_definitions").insert(row).execute()
    )
    if not result.data:
        raise ValidationError("Failed to create agent")
    agent = result.data[0]

    # Auto-create the owner's AgentInstance
    await _get_or_create_instance(supabase, agent["id"], current_user.id)
    return agent


@router.get("/{agent_id}")
async def get_agent(
    agent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    return await _get_agent(supabase, str(agent_id), current_user.id)


@router.patch("/{agent_id}")
async def update_agent(
    agent_id: UUID,
    body: UpdateAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    aid = str(agent_id)
    await _require_owner(supabase, aid, current_user.id)

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.instructions is not None:
        updates["instructions"] = body.instructions
    if body.visibility is not None:
        # Can only set to public if instructions non-empty
        if body.visibility == "public":
            agent = await _require_owner(supabase, aid, current_user.id)
            instructions = body.instructions or agent.get("instructions", "")
            if not instructions or not instructions.strip():
                raise ValidationError(
                    "instructions must not be empty before setting visibility to public"
                )
        updates["visibility"] = body.visibility
    if body.mcp_enabled is not None:
        updates["mcp_enabled"] = body.mcp_enabled

    if not updates:
        return await _require_owner(supabase, aid, current_user.id)

    result = await _run(
        lambda: supabase.table("agent_definitions")
        .update(updates)
        .eq("id", aid)
        .eq("owner_id", current_user.id)
        .execute()
    )
    if not result.data:
        raise NotFoundError("Agent not found")
    return result.data[0]


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_agent(
    agent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    supabase = get_supabase_client()
    aid = str(agent_id)
    agent = await _require_owner(supabase, aid, current_user.id)

    # Block delete if public and has external invokers
    if agent.get("visibility") == "public":
        instances = await _run(
            lambda: supabase.table("agent_instances")
            .select("id")
            .eq("agent_definition_id", aid)
            .neq("user_id", current_user.id)
            .execute()
        )
        if instances.data:
            raise ConflictError(
                "Cannot delete a public agent that has been invoked by other users. "
                "Set visibility to private or transfer the agent first."
            )

    await _run(
        lambda: supabase.table("agent_definitions")
        .delete()
        .eq("id", aid)
        .eq("owner_id", current_user.id)
        .execute()
    )


@router.post("/{agent_id}/generate-instructions")
async def generate_instructions(
    agent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Auto-generate system prompt from the agent's KB. Returns a draft."""
    supabase = get_supabase_client()
    aid = str(agent_id)
    await _require_owner(supabase, aid, current_user.id)

    # Check user has a BYOK key
    keys = await _run(
        lambda: supabase.table("user_api_keys")
        .select("provider")
        .eq("user_id", current_user.id)
        .execute()
    )
    if not keys.data:
        raise PaymentRequiredError(
            "At least one API key must be configured to generate instructions."
        )

    # TODO: full generate-instructions pipeline (Sprint 5)
    raise ValidationError("generate-instructions not yet implemented")


# ---------------------------------------------------------------------------
# AgentInstance endpoints
# ---------------------------------------------------------------------------


async def _get_or_create_instance(
    supabase: Any, agent_definition_id: str, user_id: str
) -> dict:
    """Get-or-create AgentInstance. Handles concurrent first-invocation race."""
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

    # Create — ON CONFLICT (unique constraint) is handled at DB level
    try:
        ins = await _run(
            lambda: supabase.table("agent_instances")
            .insert(
                {
                    "agent_definition_id": agent_definition_id,
                    "user_id": user_id,
                    "framework_overrides": {},
                }
            )
            .execute()
        )
        if ins.data:
            return ins.data[0]
    except Exception:
        pass  # Race condition — re-fetch below

    refetch = await _run(
        lambda: supabase.table("agent_instances")
        .select("*")
        .eq("agent_definition_id", agent_definition_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not refetch.data:
        raise ValidationError("Failed to create agent instance")
    return refetch.data


@router.get("/{agent_id}/instance")
async def get_instance(
    agent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Get or auto-create the caller's AgentInstance for this definition."""
    supabase = get_supabase_client()
    aid = str(agent_id)
    # Verify agent is accessible
    await _get_agent(supabase, aid, current_user.id)
    return await _get_or_create_instance(supabase, aid, current_user.id)


@router.patch("/{agent_id}/instance")
async def update_instance(
    agent_id: UUID,
    body: UpdateInstanceRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    aid = str(agent_id)
    await _get_agent(supabase, aid, current_user.id)
    instance = await _get_or_create_instance(supabase, aid, current_user.id)

    updates: dict = {}
    if body.framework_overrides is not None:
        # Validate pinned/excluded keys
        overrides = body.framework_overrides
        if not isinstance(overrides, dict):
            raise ValidationError("framework_overrides must be a JSON object")
        updates["framework_overrides"] = {
            "pinned": overrides.get("pinned", []),
            "excluded": overrides.get("excluded", []),
        }

    if not updates:
        return instance

    result = await _run(
        lambda: supabase.table("agent_instances")
        .update(updates)
        .eq("id", instance["id"])
        .eq("user_id", current_user.id)
        .execute()
    )
    if not result.data:
        raise NotFoundError("Agent instance not found")
    return result.data[0]
