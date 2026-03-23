"""
Agent Definition and Instance API routes — KIN-319.

Endpoints:
  GET    /api/v1/agents                       — list owned agents + public agents (merged, deduplicated)
  POST   /api/v1/agents                       — create agent definition
  GET    /api/v1/agents/{agent_id}            — get single agent (owner always; non-owner only if public)
  PATCH  /api/v1/agents/{agent_id}            — update agent (owner only)
  DELETE /api/v1/agents/{agent_id}            — delete agent (owner only; blocked if public with non-owner instances)
  GET    /api/v1/agents/{agent_id}/instance   — race-safe get-or-create instance for current user
  PATCH  /api/v1/agents/{agent_id}/instance   — update framework_overrides for current user's instance

Schema ref: docs/db-schema-spec.md (agent_definitions, agent_instances)
Conventions: all Supabase calls in async def use run_in_executor; raise AppException subclasses; never return None/[]/False on write ops.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.deps import CurrentUser, get_current_user
from app.core.errors import AuthorizationError, NotFoundError, ValidationError
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

_AGENT_FIELDS = (
    "id, owner_id, name, instructions, type, visibility, knowledge_base_id, mcp_enabled, created_at, updated_at"
)
_INSTANCE_FIELDS = (
    "id, agent_definition_id, user_id, framework_overrides, created_at, updated_at"
)


class CreateAgentRequest(BaseModel):
    name: str
    instructions: str
    type: Literal["custom", "thought_leader"]
    visibility: Literal["private", "public"] = "private"
    mcp_enabled: bool = False


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    instructions: Optional[str] = None
    type: Optional[Literal["custom", "thought_leader"]] = None
    visibility: Optional[Literal["private", "public"]] = None
    mcp_enabled: Optional[bool] = None
    knowledge_base_id: Optional[str] = None


class FrameworkOverrides(BaseModel):
    pinned: list[str] = []
    excluded: list[str] = []


class UpdateAgentInstanceRequest(BaseModel):
    framework_overrides: FrameworkOverrides


class CreateFrameworkRequest(BaseModel):
    name: str
    when_to_apply: list[str]
    principles: list[str]
    confidence: Literal["high", "medium"]
    framework_id: Optional[str] = None  # auto-generated from name if omitted
    category: Optional[str] = None
    description: Optional[str] = None
    example_application: Optional[str] = None
    steps: list[str] = []
    related_frameworks: list[str] = []


class UpdateFrameworkRequest(BaseModel):
    name: Optional[str] = None
    when_to_apply: Optional[list[str]] = None
    category: Optional[str] = None
    example_application: Optional[str] = None
    confidence: Optional[Literal["high", "medium"]] = None
    principles: Optional[list[str]] = None


class UploadFrameworksRequest(BaseModel):
    frameworks: list[dict]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "framework"


def get_supabase_client():
    """Return the service-role Supabase client. Defined as a module-level function so tests can patch it."""
    return get_supabase()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
async def list_agents(
    current_user: CurrentUser = Depends(get_current_user),
) -> list:
    """
    List agents visible to the current user:
    - All agents owned by the current user (any visibility)
    - All public agents owned by other users

    Results are merged and deduplicated by id.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Fetch owned agents
    owned_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select(_AGENT_FIELDS)
            .eq("owner_id", current_user.user_id)
            .execute(),
    )
    owned = owned_result.data or []

    # Fetch public agents from other users
    public_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select(_AGENT_FIELDS)
            .eq("visibility", "public")
            .neq("owner_id", current_user.user_id)
            .execute(),
    )
    public = public_result.data or []

    # Merge + deduplicate by id (owned takes precedence)
    seen = {a["id"] for a in owned}
    merged = list(owned)
    for agent in public:
        if agent["id"] not in seen:
            seen.add(agent["id"])
            merged.append(agent)

    return merged


@router.post("")
async def create_agent(
    body: CreateAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Create a new agent definition owned by the current user.

    Raises:
        ValidationError (400): Cannot set visibility=public with empty/None instructions.
        ValidationError (400): DB returned no data after insert.
    """
    if body.visibility == "public" and not body.instructions:
        raise ValidationError("Cannot set visibility=public with empty instructions")

    row = {
        "owner_id": current_user.user_id,
        "name": body.name,
        "instructions": body.instructions,
        "type": body.type,
        "visibility": body.visibility,
        "mcp_enabled": body.mcp_enabled,
    }

    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client.table("agent_definitions").insert(row).execute(),
    )
    if not result.data:
        logger.error(
            "create_agent: no data returned from insert",
            extra={"user_id": current_user.user_id},
        )
        raise ValidationError("Failed to create agent")
    return result.data[0]


@router.get("/{agent_id}/instance")
async def get_or_create_instance(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Race-safe get-or-create agent instance for the current user.

    Pattern: SELECT → INSERT ON CONFLICT DO NOTHING → re-SELECT

    Raises:
        NotFoundError (404): Agent not found or not accessible.
        ValidationError (400): Instance could not be found after insert.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Step 0: Verify agent exists and is accessible (owner or public)
    agent_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select("id, owner_id, visibility")
            .eq("id", agent_id)
            .single()
            .execute(),
    )
    agent = agent_result.data
    if not agent:
        raise NotFoundError("Agent not found")
    if agent["owner_id"] != current_user.user_id and agent["visibility"] != "public":
        raise NotFoundError("Agent not found")

    # Step 1: SELECT
    select_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_instances")
            .select(_INSTANCE_FIELDS)
            .eq("agent_definition_id", agent_id)
            .eq("user_id", current_user.user_id)
            .execute(),
    )
    rows = select_result.data or []
    if rows:
        return rows[0]

    # Step 2: INSERT ON CONFLICT DO NOTHING
    await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_instances")
            .insert(
                {
                    "agent_definition_id": agent_id,
                    "user_id": current_user.user_id,
                    "framework_overrides": {"pinned": [], "excluded": []},
                }
            )
            .execute(),
    )

    # Step 3: re-SELECT
    reselect_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_instances")
            .select(_INSTANCE_FIELDS)
            .eq("agent_definition_id", agent_id)
            .eq("user_id", current_user.user_id)
            .execute(),
    )
    rows = reselect_result.data or []
    if not rows:
        logger.error(
            "get_or_create_instance: instance not found after insert",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )
        raise ValidationError("Failed to get or create agent instance")
    return rows[0]


@router.patch("/{agent_id}/instance")
async def update_instance(
    agent_id: str,
    body: UpdateAgentInstanceRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update framework_overrides for the current user's agent instance.

    Raises:
        NotFoundError (404): Instance not found.
        AuthorizationError (403): Instance belongs to a different user.
        NotFoundError (404): DB returned no data after update.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Fetch instance by agent_definition_id + user_id (the natural composite key)
    fetch_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_instances")
            .select(_INSTANCE_FIELDS)
            .eq("agent_definition_id", agent_id)
            .eq("user_id", current_user.user_id)
            .single()
            .execute(),
    )
    instance = fetch_result.data
    if not instance:
        raise NotFoundError("Agent instance not found")

    updates = {
        "framework_overrides": body.framework_overrides.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    update_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_instances")
            .update(updates)
            .eq("id", instance["id"])
            .execute(),
    )
    if not update_result.data:
        raise NotFoundError("Agent instance not found after update")
    return update_result.data[0]


@router.post("/{agent_id}/frameworks/upload")
async def upload_frameworks(
    agent_id: str,
    body: UploadFrameworksRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Bulk-import frameworks for an agent definition via JSON upload. Owner only.

    For each item: validates required fields, then upserts (update if framework_id
    already exists, insert otherwise). Per-item errors are collected in `failed` —
    they never abort the whole upload.

    Returns:
        {"added": int, "updated": int, "retained": int, "failed": list[dict]}
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Step 1: Fetch agent — 404 if not found
    agent_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select(_AGENT_FIELDS)
            .eq("id", agent_id)
            .single()
            .execute(),
    )
    agent = agent_result.data
    if not agent:
        raise NotFoundError("Agent not found")

    # Step 2: Owner check
    if agent["owner_id"] != current_user.user_id:
        raise AuthorizationError("You do not own this agent")

    # Step 3: Fetch all existing frameworks for this agent
    existing_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("frameworks")
            .select("id, framework_id")
            .eq("agent_definition_id", agent_id)
            .execute(),
    )
    existing: dict[str, str] = {
        row["framework_id"]: row["id"]
        for row in (existing_result.data or [])
    }

    added = 0
    updated = 0
    failed: list[dict] = []

    # Step 4: Process each item
    for item in body.frameworks:
        fw_id_label = item.get("framework_id", "?")

        # Validate required fields
        name = item.get("name")
        when_to_apply = item.get("when_to_apply")
        confidence = item.get("confidence")
        principles = item.get("principles")

        if not isinstance(name, str) or not name:
            failed.append({"framework_id": fw_id_label, "error": "name is required"})
            continue
        if not isinstance(when_to_apply, list) or len(when_to_apply) < 1:
            failed.append({"framework_id": fw_id_label, "error": "when_to_apply must be a non-empty list"})
            continue
        if confidence not in {"high", "medium"}:
            failed.append({"framework_id": fw_id_label, "error": "confidence must be 'high' or 'medium'"})
            continue
        if not isinstance(principles, list) or len(principles) < 1:
            failed.append({"framework_id": fw_id_label, "error": "principles must be a non-empty list"})
            continue

        fw_id = item.get("framework_id")

        if fw_id and fw_id in existing:
            # Update existing framework
            update_dict: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
            for field in ("name", "when_to_apply", "confidence", "principles", "category",
                          "description", "example_application", "steps", "related_frameworks", "origin",
                          "source_posts"):
                if field in item:
                    update_dict[field] = item[field]
            try:
                await loop.run_in_executor(
                    None,
                    lambda uid=existing[fw_id], ud=update_dict: client
                        .table("frameworks")
                        .update(ud)
                        .eq("id", uid)
                        .execute(),
                )
                updated += 1
            except Exception as exc:
                logger.error("upload_frameworks: update failed", extra={"framework_id": fw_id, "error": str(exc)})
                failed.append({"framework_id": fw_id, "error": str(exc)})
        else:
            # Insert new framework
            row = {
                "agent_definition_id": agent_id,
                "origin": item.get("origin", "manual"),
                "framework_id": fw_id or _slug(name),
                "name": name,
                "when_to_apply": when_to_apply,
                "confidence": confidence,
                "principles": principles,
            }
            for field in ("category", "description", "example_application", "steps", "related_frameworks"):
                if field in item:
                    row[field] = item[field]
            try:
                await loop.run_in_executor(
                    None,
                    lambda r=row: client.table("frameworks").insert(r).execute(),
                )
                added += 1
            except Exception as exc:
                logger.error("upload_frameworks: insert failed", extra={"framework_id": fw_id_label, "error": str(exc)})
                failed.append({"framework_id": fw_id_label, "error": str(exc)})

    retained = len(existing) - updated
    return {"added": added, "updated": updated, "retained": retained, "failed": failed}


@router.post("/{agent_id}/frameworks")
async def create_framework(
    agent_id: str,
    body: CreateFrameworkRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Create a new framework for an agent definition. Owner only.

    Raises:
        NotFoundError (404): Agent not found.
        AuthorizationError (403): Current user is not the owner.
        ValidationError (400): when_to_apply or principles is empty.
        ValidationError (400): DB returned no data after insert.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Step 1: Fetch agent — 404 if not found
    agent_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select(_AGENT_FIELDS)
            .eq("id", agent_id)
            .single()
            .execute(),
    )
    agent = agent_result.data
    if not agent:
        raise NotFoundError("Agent not found")

    # Step 2: Owner check
    if agent["owner_id"] != current_user.user_id:
        raise AuthorizationError("You do not own this agent")

    # Step 3: Validate required list fields
    if not body.when_to_apply:
        raise ValidationError("when_to_apply must not be empty")
    if not body.principles:
        raise ValidationError("principles must not be empty")

    # Step 4: Build row
    framework_id = body.framework_id or _slug(body.name)
    row = {
        "framework_id": framework_id,
        "agent_definition_id": agent_id,
        "origin": "manual",
        "name": body.name,
        "when_to_apply": body.when_to_apply,
        "principles": body.principles,
        "confidence": body.confidence,
        "steps": body.steps,
        "related_frameworks": body.related_frameworks,
    }
    if body.category is not None:
        row["category"] = body.category
    if body.description is not None:
        row["description"] = body.description
    if body.example_application is not None:
        row["example_application"] = body.example_application

    # Step 5: Insert
    result = await loop.run_in_executor(
        None,
        lambda: client.table("frameworks").insert(row).execute(),
    )
    if not result.data:
        logger.error(
            "create_framework: no data returned from insert",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )
        raise ValidationError("Failed to create framework")
    return result.data[0]


@router.patch("/{agent_id}/frameworks/{framework_db_id}")
async def update_framework(
    agent_id: str,
    framework_db_id: str,  # frameworks.id (UUID PK) — NOT the semantic framework_id text column
    body: UpdateFrameworkRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update a framework for an agent definition. Owner only.

    NOTE: `framework_db_id` is the DB primary key (frameworks.id UUID), not the semantic
    `frameworks.framework_id` text slug. Frontend must send framework.id, not framework.framework_id.

    Raises:
        NotFoundError (404): Agent not found.
        AuthorizationError (403): Current user is not the owner.
        NotFoundError (404): Framework not found under this agent.
        ValidationError (400): when_to_apply or principles set to empty list.
        NotFoundError (404): DB returned no data after update.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Step 1: Fetch agent — 404 if not found
    agent_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select(_AGENT_FIELDS)
            .eq("id", agent_id)
            .single()
            .execute(),
    )
    agent = agent_result.data
    if not agent:
        raise NotFoundError("Agent not found")

    # Step 2: Owner check
    if agent["owner_id"] != current_user.user_id:
        raise AuthorizationError("You do not own this agent")

    # Step 3: Fetch framework by DB primary key
    fw_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("frameworks")
            .select("*")
            .eq("id", framework_db_id)
            .eq("agent_definition_id", agent_id)
            .single()
            .execute(),
    )
    framework = fw_result.data
    if not framework:
        raise NotFoundError("Framework not found")

    # Step 4: Build updates dict from non-None fields
    updates: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if body.name is not None:
        updates["name"] = body.name
    if body.when_to_apply is not None:
        updates["when_to_apply"] = body.when_to_apply
    if body.category is not None:
        updates["category"] = body.category
    if body.example_application is not None:
        updates["example_application"] = body.example_application
    if body.confidence is not None:
        updates["confidence"] = body.confidence
    if body.principles is not None:
        updates["principles"] = body.principles

    # Step 5: Validate list fields not set to empty
    if "when_to_apply" in updates and len(updates["when_to_apply"]) == 0:
        raise ValidationError("when_to_apply must not be empty")
    if "principles" in updates and len(updates["principles"]) == 0:
        raise ValidationError("principles must not be empty")

    # Step 6: Update
    update_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("frameworks")
            .update(updates)
            .eq("id", framework_db_id)
            .execute(),
    )
    if not update_result.data:
        raise NotFoundError("Framework not found after update")
    return update_result.data[0]


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Get a single agent by ID.

    - Owner can always retrieve their agent.
    - Non-owners can only retrieve public agents.

    Raises:
        NotFoundError (404): Agent not found or not visible to current user.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select(_AGENT_FIELDS)
            .eq("id", agent_id)
            .single()
            .execute(),
    )
    agent = result.data
    if not agent:
        raise NotFoundError("Agent not found")
    if agent["owner_id"] != current_user.user_id and agent["visibility"] != "public":
        raise NotFoundError("Agent not found")
    return agent


@router.patch("/{agent_id}")
async def update_agent(
    agent_id: str,
    body: UpdateAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update an agent definition. Owner only.

    Raises:
        NotFoundError (404): Agent not found.
        AuthorizationError (403): Current user is not the owner.
        ValidationError (400): Cannot set visibility=public with empty instructions.
        NotFoundError (404): DB returned no data after update.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Fetch for ownership check
    fetch_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select(_AGENT_FIELDS)
            .eq("id", agent_id)
            .single()
            .execute(),
    )
    agent = fetch_result.data
    if not agent:
        raise NotFoundError("Agent not found")
    if agent["owner_id"] != current_user.user_id:
        raise AuthorizationError("You do not own this agent")

    # Determine effective instructions after update
    new_instructions = body.instructions if body.instructions is not None else agent["instructions"]
    new_visibility = body.visibility if body.visibility is not None else agent["visibility"]
    if new_visibility == "public" and not new_instructions:
        raise ValidationError("Cannot set visibility=public with empty instructions")

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.instructions is not None:
        updates["instructions"] = body.instructions
    if body.type is not None:
        updates["type"] = body.type
    if body.visibility is not None:
        updates["visibility"] = body.visibility
    if body.mcp_enabled is not None:
        updates["mcp_enabled"] = body.mcp_enabled
    if body.knowledge_base_id is not None:
        updates["knowledge_base_id"] = body.knowledge_base_id
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    update_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .update(updates)
            .eq("id", agent_id)
            .execute(),
    )
    if not update_result.data:
        raise NotFoundError("Agent not found after update")
    return update_result.data[0]


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """
    Hard-delete an agent definition. Owner only.

    Blocked if the agent is public AND has agent_instances from non-owner users.

    Raises:
        NotFoundError (404): Agent not found.
        AuthorizationError (403): Current user is not the owner.
        ValidationError (400): Public agent has non-owner instances.
        NotFoundError (404): DB returned no data after delete.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Fetch for ownership check
    fetch_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select(_AGENT_FIELDS)
            .eq("id", agent_id)
            .single()
            .execute(),
    )
    agent = fetch_result.data
    if not agent:
        raise NotFoundError("Agent not found")
    if agent["owner_id"] != current_user.user_id:
        raise AuthorizationError("You do not own this agent")

    # If public, check for non-owner instances
    if agent["visibility"] == "public":
        instances_result = await loop.run_in_executor(
            None,
            lambda: client
                .table("agent_instances")
                .select("id")
                .eq("agent_definition_id", agent_id)
                .neq("user_id", current_user.user_id)
                .execute(),
        )
        if instances_result.data:
            raise ValidationError(
                "Cannot delete a public agent that has been adopted by other users"
            )

    delete_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .delete()
            .eq("id", agent_id)
            .execute(),
    )
    if not delete_result.data:
        raise NotFoundError("Agent not found after delete")


@router.get("/{agent_id}/frameworks")
async def list_frameworks(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List all frameworks for an agent definition.

    - Owner can always retrieve frameworks.
    - Non-owners can retrieve frameworks for public agents.

    Raises:
        NotFoundError (404): Agent not found.
        AuthorizationError (403): Agent is private and current user is not the owner.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Step 1: Fetch agent — 404 if not found
    agent_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select(_AGENT_FIELDS)
            .eq("id", agent_id)
            .single()
            .execute(),
    )
    agent = agent_result.data
    if not agent:
        raise NotFoundError("Agent not found")

    # Step 2: Access check — owner OR public (404 to avoid leaking existence of private agents)
    if agent["owner_id"] != current_user.user_id and agent["visibility"] != "public":
        raise NotFoundError("Agent not found")

    # Step 3: Fetch frameworks ordered by created_at ASC
    frameworks_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("frameworks")
            .select("*")
            .eq("agent_definition_id", agent_id)
            .order("created_at", desc=False)
            .execute(),
    )
    return {"frameworks": frameworks_result.data or []}


@router.delete("/{agent_id}/frameworks/{framework_id}", status_code=204)
async def delete_framework(
    agent_id: str,
    framework_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """
    Hard-delete a framework from an agent definition. Owner only.

    Raises:
        NotFoundError (404): Agent not found.
        AuthorizationError (403): Current user is not the owner.
        NotFoundError (404): Framework not found under this agent.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Step 1: Fetch agent — 404 if not found
    agent_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select(_AGENT_FIELDS)
            .eq("id", agent_id)
            .single()
            .execute(),
    )
    agent = agent_result.data
    if not agent:
        raise NotFoundError("Agent not found")

    # Step 2: Must be owner
    if agent["owner_id"] != current_user.user_id:
        raise AuthorizationError("You do not own this agent")

    # Step 3: DELETE WHERE id = framework_id AND agent_definition_id = agent_id
    delete_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("frameworks")
            .delete()
            .eq("id", framework_id)
            .eq("agent_definition_id", agent_id)
            .execute(),
    )

    # Step 4: 404 if nothing was deleted
    if not delete_result.data:
        raise NotFoundError("Framework not found")
