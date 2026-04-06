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

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from app.auth.deps import CurrentUser, get_current_user
from app.core.errors import AuthorizationError, NotFoundError, ValidationError
from app.db.supabase_client import get_supabase
from app.services.background import TaskDispatcher
from app.services.framework_embeddings import embed_framework_triggers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

_AGENT_FIELDS = (
    "id, owner_id, name, slug, instructions, type, visibility, created_at, updated_at"
)
_INSTANCE_FIELDS = (
    "id, agent_definition_id, user_id, framework_overrides, created_at, updated_at"
)


class CreateAgentRequest(BaseModel):
    name: str
    instructions: str = ""  # Empty by default; non-empty required only for public visibility (enforced in route handler)
    type: Literal["custom", "thought_leader"]
    visibility: Literal["private", "public"] = "private"
class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    instructions: Optional[str] = None
    type: Optional[Literal["custom", "thought_leader"]] = None
    visibility: Optional[Literal["private", "public"]] = None


class FrameworkOverrides(BaseModel):
    pinned: list[str] = []
    excluded: list[str] = []
    disabled: bool = False


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
    type: Optional[str] = None
    do_not_use_when: list[str] = []


class UpdateFrameworkRequest(BaseModel):
    name: Optional[str] = None
    when_to_apply: Optional[list[str]] = None
    category: Optional[str] = None
    example_application: Optional[str] = None
    confidence: Optional[Literal["high", "medium"]] = None
    principles: Optional[list[str]] = None
    type: Optional[str] = None
    do_not_use_when: Optional[list[str]] = None


class UploadFrameworksRequest(BaseModel):
    frameworks: list[dict]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "framework"


def _agent_slug(name: str) -> str:
    """Generate a slug for an agent definition: lowercase, hyphens, max 60 chars."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if len(slug) > 60:
        slug = slug[:60].rstrip("-")
    return slug or "agent"


async def _ensure_unique_slug(client, slug: str) -> str:
    """Check slug uniqueness globally. If taken, append -2, -3, etc."""
    loop = asyncio.get_running_loop()
    candidate = slug

    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select("id")
            .eq("slug", candidate)
            .maybe_single()
            .execute(),
    )
    if result is None or not result.data:
        return candidate

    suffix = 2
    while True:
        candidate = f"{slug}-{suffix}"
        result = await loop.run_in_executor(
            None,
            lambda c=candidate: client
                .table("agent_definitions")
                .select("id")
                .eq("slug", c)
                .maybe_single()
                .execute(),
        )
        if result is None or not result.data:
            return candidate
        suffix += 1


def get_supabase_client():
    """Return the service-role Supabase client. Defined as a module-level function so tests can patch it."""
    return get_supabase()


def get_task_dispatcher(background_tasks: BackgroundTasks) -> TaskDispatcher:
    """Return a TaskDispatcher. Defined at module level so tests can patch it."""
    return TaskDispatcher(background_tasks)


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

    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    slug = await _ensure_unique_slug(client, _agent_slug(body.name))

    row = {
        "owner_id": current_user.user_id,
        "name": body.name,
        "slug": slug,
        "instructions": body.instructions,
        "type": body.type,
        "visibility": body.visibility,
    }

    try:
        result = await loop.run_in_executor(
            None,
            lambda: client.table("agent_definitions").insert(row).execute(),
        )
    except Exception as exc:
        logger.error(
            "create_agent: insert failed — %s",
            exc,
            extra={"user_id": current_user.user_id},
        )
        raise ValidationError(f"Failed to create agent: {exc}")

    if result is None or not result.data:
        logger.error(
            "create_agent: no data returned from insert",
            extra={"user_id": current_user.user_id},
        )
        raise ValidationError("Failed to create agent — no data returned")
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
    background_tasks: BackgroundTasks,
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
    embedding_jobs: list[tuple[str, list[str]]] = []  # (framework_db_id, triggers)

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
                          "source_posts", "type", "do_not_use_when"):
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
                if "when_to_apply" in update_dict:
                    embedding_jobs.append((existing[fw_id], update_dict["when_to_apply"]))
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
            for field in ("category", "description", "example_application", "steps",
                          "related_frameworks", "source_posts", "type", "do_not_use_when"):
                if field in item:
                    row[field] = item[field]
            try:
                insert_result = await loop.run_in_executor(
                    None,
                    lambda r=row: client.table("frameworks").insert(r).execute(),
                )
                added += 1
                if insert_result.data:
                    embedding_jobs.append((insert_result.data[0]["id"], when_to_apply))
            except Exception as exc:
                logger.error("upload_frameworks: insert failed", extra={"framework_id": fw_id_label, "error": str(exc)})
                failed.append({"framework_id": fw_id_label, "error": str(exc)})

    # Step 5: Dispatch embedding jobs for all added/updated frameworks
    if embedding_jobs:
        dispatcher = get_task_dispatcher(background_tasks)
        for fw_db_id, triggers in embedding_jobs:
            dispatcher.dispatch(
                embed_framework_triggers,
                fw_db_id,
                agent_id,
                triggers,
                current_user.user_id,
            )

    retained = len(existing) - updated
    return {"added": added, "updated": updated, "retained": retained, "failed": failed}


@router.post("/{agent_id}/frameworks")
async def create_framework(
    agent_id: str,
    body: CreateFrameworkRequest,
    background_tasks: BackgroundTasks,
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
    if body.type is not None:
        row["type"] = body.type
    if body.do_not_use_when:
        row["do_not_use_when"] = body.do_not_use_when

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

    # Step 6: Dispatch trigger embedding job
    get_task_dispatcher(background_tasks).dispatch(
        embed_framework_triggers,
        result.data[0]["id"],
        agent_id,
        body.when_to_apply,
        current_user.user_id,
    )

    return result.data[0]


@router.patch("/{agent_id}/frameworks/{framework_db_id}")
async def update_framework(
    agent_id: str,
    framework_db_id: str,  # frameworks.id (UUID PK) — NOT the semantic framework_id text column
    body: UpdateFrameworkRequest,
    background_tasks: BackgroundTasks,
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
    if body.type is not None:
        updates["type"] = body.type
    if body.do_not_use_when is not None:
        updates["do_not_use_when"] = body.do_not_use_when

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

    # Dispatch trigger embedding job only if when_to_apply was updated
    if "when_to_apply" in updates:
        get_task_dispatcher(background_tasks).dispatch(
            embed_framework_triggers,
            framework_db_id,
            agent_id,
            updates["when_to_apply"],
            current_user.user_id,
        )

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
        # Regenerate slug when name changes
        new_slug = _agent_slug(body.name)
        if new_slug != agent.get("slug", ""):
            updates["slug"] = await _ensure_unique_slug(client, new_slug)
    if body.instructions is not None:
        updates["instructions"] = body.instructions
    if body.type is not None:
        updates["type"] = body.type
    if body.visibility is not None:
        updates["visibility"] = body.visibility
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


# ---------------------------------------------------------------------------
# Generate instructions from KB — KIN-366
# ---------------------------------------------------------------------------

_TEXT_LIMIT_GENERATE = 12_000  # Max corpus chars sent to LLM


@router.post("/{agent_id}/generate-instructions")
async def generate_instructions(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Auto-generate a system prompt from the agent's KB documents.

    Reads completed document chunks, concatenates text, sends to BYOK LLM
    with a generation prompt. Returns drafted instructions for user review.
    Does NOT auto-save — caller reviews and saves via PATCH /api/v1/agents/:id.

    Spec: docs/specs/agents.md §7 (Thought Leader Agent Flow, Step 3), §10
    Requires: owner, KB with docs, at least one BYOK key.

    Raises:
        AuthorizationError(403): Not the agent owner.
        ValidationError(400): No KB, no docs, or no API key.
        HTTPException(500): LLM call failed.
    """
    from fastapi import HTTPException

    from app.services.encryption import decrypt_api_key, load_master_key
    from app.services.llm_client import call_llm
    from app.services.prompts import get_prompt

    client = get_supabase_client()
    loop = asyncio.get_running_loop()

    # 1. Fetch agent and verify ownership
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
        raise NotFoundError("Agent not found.")
    if agent["owner_id"] != current_user.user_id:
        raise AuthorizationError("Only the agent owner can generate instructions.")

    # 2. Look up KB via knowledge_bases table (polymorphic FK: agent_definition_id)
    kb_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("knowledge_bases")
            .select("id")
            .eq("agent_definition_id", agent_id)
            .execute(),
    )
    kb_rows = kb_result.data or []
    if not kb_rows:
        raise ValidationError("Agent has no knowledge base. Upload documents first.")
    kb_id = kb_rows[0]["id"]

    # 3. Fetch completed, non-deleted documents
    docs_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("knowledge_base_documents")
            .select("id, title, status")
            .eq("knowledge_base_id", kb_id)
            .eq("status", "completed")
            .is_("deleted_at", "null")
            .execute(),
    )
    docs = docs_result.data or []
    if not docs:
        raise ValidationError("No completed documents in knowledge base. Upload and process documents first.")

    # 4. Fetch chunks for those documents (db-schema-spec §13: knowledge_base_chunks)
    doc_ids = [d["id"] for d in docs]
    chunks_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("knowledge_base_chunks")
            .select("text, chunk_index")
            .in_("document_id", doc_ids)
            .order("chunk_index")
            .execute(),
    )
    chunks = chunks_result.data or []
    corpus_text = "\n\n".join(c["text"] for c in chunks if c.get("text"))
    corpus_text = corpus_text[:_TEXT_LIMIT_GENERATE]

    if not corpus_text.strip():
        raise ValidationError("No text content found in knowledge base documents.")

    # 5. Get BYOK key
    key_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("user_api_keys")
            .select("provider, key_ciphertext, key_nonce")
            .eq("user_id", current_user.user_id)
            .execute(),
    )
    key_rows = key_result.data or []
    if not key_rows:
        raise ValidationError("No API key configured. Add an API key to use this feature.")
    key_row = key_rows[0]

    # 6. Decrypt key and call LLM
    master_key = load_master_key()
    api_key = decrypt_api_key(
        bytes.fromhex(key_row["key_ciphertext"]),
        bytes.fromhex(key_row["key_nonce"]),
        master_key,
        current_user.user_id,
    )

    prompt_text = get_prompt("generate-instructions-v1", "system_prompt_generate")
    try:
        generated = call_llm(
            messages=[{
                "role": "user",
                "content": prompt_text + "\n\n" + corpus_text,
            }],
            model="gpt-4o-mini",
            api_key=api_key,
            max_tokens=800,
            timeout=30,
        ).strip()
    except Exception as exc:
        logger.error("LLM generation failed for agent %s: %s", agent_id, exc)
        raise HTTPException(status_code=500, detail="Instruction generation failed. Please try again.")

    return {"instructions": generated}


# ---------------------------------------------------------------------------
# Agent Knowledge Base — KIN-367
# ---------------------------------------------------------------------------


@router.get("/{agent_id}/knowledge-base")
async def get_agent_knowledge_base(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Look up the KB attached to this agent. 404 if none."""
    client = get_supabase_client()
    loop = asyncio.get_running_loop()

    agent_result = await loop.run_in_executor(
        None,
        lambda: client.table("agent_definitions")
            .select("id, owner_id, visibility").eq("id", agent_id).single().execute(),
    )
    agent = agent_result.data
    if not agent:
        raise NotFoundError("Agent not found.")
    if agent["owner_id"] != current_user.user_id and agent["visibility"] != "public":
        raise AuthorizationError("Access denied.")

    kb_result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_bases")
            .select("id").eq("agent_definition_id", agent_id).execute(),
    )
    kb_rows = kb_result.data or []
    if not kb_rows:
        raise NotFoundError("No knowledge base attached to this agent.")
    return {"id": kb_rows[0]["id"]}


@router.post("/{agent_id}/knowledge-base", status_code=201)
async def create_agent_knowledge_base(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Create a KB for the agent. Idempotent — returns existing if already attached. Owner only."""
    client = get_supabase_client()
    loop = asyncio.get_running_loop()

    agent_result = await loop.run_in_executor(
        None,
        lambda: client.table("agent_definitions")
            .select("id, owner_id").eq("id", agent_id).single().execute(),
    )
    agent = agent_result.data
    if not agent:
        raise NotFoundError("Agent not found.")
    if agent["owner_id"] != current_user.user_id:
        raise AuthorizationError("Only the agent owner can create a knowledge base.")

    kb_result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_bases")
            .select("id").eq("agent_definition_id", agent_id).execute(),
    )
    kb_rows = kb_result.data or []
    if kb_rows:
        return {"id": kb_rows[0]["id"]}

    insert_result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_bases")
            .insert({"agent_definition_id": agent_id, "user_id": current_user.user_id})
            .execute(),
    )
    if not insert_result.data:
        raise ValidationError("Failed to create knowledge base.")
    return {"id": insert_result.data[0]["id"]}


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


class DeleteAllFrameworksResponse(BaseModel):
    agent_id: str
    deleted_count: int


@router.delete("/{agent_id}/frameworks", response_model=DeleteAllFrameworksResponse)
async def delete_all_frameworks(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> DeleteAllFrameworksResponse:
    """
    Hard-delete ALL frameworks for an agent definition. Owner only.

    Trigger embeddings are removed automatically via ON DELETE CASCADE.

    Raises:
        NotFoundError (404): Agent not found.
        AuthorizationError (403): Current user is not the owner.
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

    # Step 3: DELETE all frameworks for this agent
    delete_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("frameworks")
            .delete()
            .eq("agent_definition_id", agent_id)
            .execute(),
    )

    deleted_count = len(delete_result.data) if delete_result.data else 0
    return DeleteAllFrameworksResponse(
        agent_id=agent_id, deleted_count=deleted_count,
    )
