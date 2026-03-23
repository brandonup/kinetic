"""
Active Memory CRUD routes — KIN-308.

Endpoints:
  GET    /api/v1/active-memory                         — list entries + token usage
  POST   /api/v1/active-memory                         — create entry (enforces token cap)
  PATCH  /api/v1/active-memory/{entry_id}              — update entry content (delta cap check)
  DELETE /api/v1/active-memory/{entry_id}              — delete entry (204)
  GET    /api/v1/active-memory/proposals               — list pending proposals for scope
  POST   /api/v1/active-memory/proposals/review        — bulk accept/reject proposals
  GET    /api/v1/admin/active-memory                   — admin: read any user's entries

Spec: docs/specs/active-memory-spec.md
Schema: docs/db-schema-spec.md §16 (active_memory_entries), §17 (memory_proposals)

Conventions:
  - All Supabase calls in async def use run_in_executor
  - Service-role client used throughout; user ownership verified via user_id equality
  - Token count: ceil(len(content) / 4) — character-proxy, no tiktoken
  - Caps: ACTIVE_MEMORY_CAP_PROJECT = 1000, ACTIVE_MEMORY_CAP_AGENT = 500
  - Never return None/[]/False on write operations — raise or log-and-raise
"""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user, require_admin
from app.core.errors import (
    AuthorizationError,
    MemoryCapExceededError,
    NotFoundError,
    ValidationError,
)
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTIVE_MEMORY_CAP_PROJECT = 1000   # tokens
ACTIVE_MEMORY_CAP_AGENT = 500      # tokens

router = APIRouter(tags=["active-memory"])
admin_router = APIRouter(prefix="/api/v1/admin/active-memory", tags=["admin-active-memory"])


# ---------------------------------------------------------------------------
# Supabase client accessor (module-level for testability)
# ---------------------------------------------------------------------------


def get_supabase_client():
    return get_supabase()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CreateEntryRequest(BaseModel):
    content: str
    project_id: Optional[str] = None
    agent_instance_id: Optional[str] = None
    source_conversation_id: Optional[str] = None

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("content must not be empty")
        return v


class UpdateEntryRequest(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("content must not be empty")
        return v


class ProposalDecision(BaseModel):
    proposal_id: str
    action: Literal["accept", "reject"]


class ReviewProposalsRequest(BaseModel):
    decisions: List[ProposalDecision]


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _count_tokens(content: str) -> int:
    """Character-proxy token count: ceil(len(content) / 4)."""
    return math.ceil(len(content) / 4)


# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------


def _resolve_scope(
    project_id: Optional[str],
    agent_instance_id: Optional[str],
) -> tuple[str, str, int]:
    """
    Validate that exactly one scope param is provided.

    Returns (scope_type, scope_id, cap) where scope_type is 'project' or 'agent_instance'.
    Raises ValidationError if both or neither are set.
    """
    if project_id is not None and agent_instance_id is not None:
        raise ValidationError("Provide either project_id or agent_instance_id, not both")
    if project_id is None and agent_instance_id is None:
        raise ValidationError("Either project_id or agent_instance_id is required")
    if project_id is not None:
        return "project", project_id, ACTIVE_MEMORY_CAP_PROJECT
    return "agent_instance", agent_instance_id, ACTIVE_MEMORY_CAP_AGENT


# ---------------------------------------------------------------------------
# Ownership verification helpers
# ---------------------------------------------------------------------------


async def _verify_project_ownership(project_id: str, user_id: str, client) -> None:
    """Raise AuthorizationError if project is not owned by user."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("projects")
            .select("id")
            .eq("id", project_id)
            .eq("user_id", user_id)
            .single()
            .execute(),
    )
    if not result.data:
        raise AuthorizationError("Project does not belong to the requesting user")


async def _verify_agent_instance_ownership(agent_instance_id: str, user_id: str, client) -> None:
    """Raise AuthorizationError if agent_instance is not owned by user."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_instances")
            .select("id")
            .eq("id", agent_instance_id)
            .eq("user_id", user_id)
            .single()
            .execute(),
    )
    if not result.data:
        raise AuthorizationError("AgentInstance does not belong to the requesting user")


async def _verify_scope_ownership(scope_type: str, scope_id: str, user_id: str, client) -> None:
    """Dispatch to the correct ownership check."""
    if scope_type == "project":
        await _verify_project_ownership(scope_id, user_id, client)
    else:
        await _verify_agent_instance_ownership(scope_id, user_id, client)


# ---------------------------------------------------------------------------
# Token cap query helper
# ---------------------------------------------------------------------------


async def _get_current_tokens(scope_col: str, scope_id: str, user_id: str, client) -> int:
    """Sum token counts of all existing entries for the scope."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("active_memory_entries")
            .select("content")
            .eq(scope_col, scope_id)
            .eq("user_id", user_id)
            .execute(),
    )
    return sum(_count_tokens(row["content"]) for row in (result.data or []))


def _scope_col(scope_type: str) -> str:
    return "project_id" if scope_type == "project" else "agent_instance_id"


# ---------------------------------------------------------------------------
# Entries — GET /api/v1/active-memory
# ---------------------------------------------------------------------------


@router.get("/api/v1/active-memory")
async def list_entries(
    project_id: Optional[str] = Query(default=None),
    agent_instance_id: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List Active Memory entries for a scope. Returns entries ordered created_at DESC plus token_usage.

    Raises:
        ValidationError (400): both or neither scope params provided.
        AuthorizationError (403): scope entity does not belong to user.
    """
    scope_type, scope_id, cap = _resolve_scope(project_id, agent_instance_id)
    col = _scope_col(scope_type)

    client = get_supabase_client()
    await _verify_scope_ownership(scope_type, scope_id, current_user.user_id, client)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("active_memory_entries")
            .select("id, content, source_conversation_id, created_at, updated_at")
            .eq(col, scope_id)
            .eq("user_id", current_user.user_id)
            .order("created_at", desc=True)
            .execute(),
    )
    entries = result.data or []
    current_tokens = sum(_count_tokens(e["content"]) for e in entries)

    return {
        "entries": entries,
        "token_usage": {"current_tokens": current_tokens, "cap_tokens": cap},
    }


# ---------------------------------------------------------------------------
# Entries — POST /api/v1/active-memory
# ---------------------------------------------------------------------------


@router.post("/api/v1/active-memory", status_code=201)
async def create_entry(
    body: CreateEntryRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Create a new Active Memory entry. Enforces token cap before insert.

    Raises:
        ValidationError (400): scope params invalid or content empty.
        AuthorizationError (403): scope entity not owned by user.
        MemoryCapExceededError (422): write would exceed the cap.
    """
    scope_type, scope_id, cap = _resolve_scope(body.project_id, body.agent_instance_id)
    col = _scope_col(scope_type)

    client = get_supabase_client()
    await _verify_scope_ownership(scope_type, scope_id, current_user.user_id, client)

    new_tokens = _count_tokens(body.content)
    current_tokens = await _get_current_tokens(col, scope_id, current_user.user_id, client)

    # Race condition: two concurrent writes both passing this check then both inserting is possible
    # at low traffic. For MVP, application-level check is sufficient; a DB-level constraint
    # (e.g., SECURITY DEFINER RPC with SELECT FOR UPDATE) would be needed for strict enforcement.
    if current_tokens + new_tokens > cap:
        raise MemoryCapExceededError(current_tokens=current_tokens, cap_tokens=cap)

    row = {
        "user_id": current_user.user_id,
        col: scope_id,
        "content": body.content,
        "source_conversation_id": body.source_conversation_id,
    }

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client.table("active_memory_entries").insert(row).execute(),
    )
    if not result.data:
        logger.error(
            "create_entry: no data returned from insert",
            extra={"user_id": current_user.user_id, col: scope_id},
        )
        raise ValidationError("Failed to create memory entry")

    return result.data[0]


# ---------------------------------------------------------------------------
# Entries — PATCH /api/v1/active-memory/{entry_id}
# ---------------------------------------------------------------------------


@router.patch("/api/v1/active-memory/{entry_id}")
async def update_entry(
    entry_id: str,
    body: UpdateEntryRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update an entry's content. Applies delta cap check: old tokens subtracted, new tokens added.

    Raises:
        NotFoundError (404): entry not found or not owned by user.
        MemoryCapExceededError (422): new content would exceed cap.
    """
    client = get_supabase_client()
    loop = asyncio.get_running_loop()

    # Fetch existing entry (ownership implicit via user_id filter)
    fetch_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("active_memory_entries")
            .select("id, content, project_id, agent_instance_id")
            .eq("id", entry_id)
            .eq("user_id", current_user.user_id)
            .single()
            .execute(),
    )
    if not fetch_result.data:
        raise NotFoundError("Memory entry not found")

    existing_entry = fetch_result.data
    old_content = existing_entry["content"]
    old_tokens = _count_tokens(old_content)

    # Determine scope from existing entry
    if existing_entry.get("project_id"):
        scope_type = "project"
        scope_id = existing_entry["project_id"]
        cap = ACTIVE_MEMORY_CAP_PROJECT
    else:
        scope_type = "agent_instance"
        scope_id = existing_entry["agent_instance_id"]
        cap = ACTIVE_MEMORY_CAP_AGENT

    col = _scope_col(scope_type)

    # Get total current tokens for scope
    current_total = await _get_current_tokens(col, scope_id, current_user.user_id, client)

    new_tokens = _count_tokens(body.content)
    new_total = current_total - old_tokens + new_tokens

    if new_total > cap:
        raise MemoryCapExceededError(current_tokens=current_total, cap_tokens=cap)

    updates = {
        "content": body.content,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    update_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("active_memory_entries")
            .update(updates)
            .eq("id", entry_id)
            .eq("user_id", current_user.user_id)
            .execute(),
    )
    if not update_result.data:
        raise NotFoundError("Memory entry not found")

    return update_result.data[0]


# ---------------------------------------------------------------------------
# Entries — DELETE /api/v1/active-memory/{entry_id}
# ---------------------------------------------------------------------------


@router.delete("/api/v1/active-memory/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """
    Delete an Active Memory entry.

    Raises:
        NotFoundError (404): entry not found or not owned by user.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("active_memory_entries")
            .delete()
            .eq("id", entry_id)
            .eq("user_id", current_user.user_id)
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Memory entry not found")


# ---------------------------------------------------------------------------
# Proposals — GET /api/v1/active-memory/proposals
# ---------------------------------------------------------------------------


@router.get("/api/v1/active-memory/proposals")
async def list_proposals(
    project_id: Optional[str] = Query(default=None),
    agent_instance_id: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List pending memory proposals for a scope.

    Raises:
        ValidationError (400): both or neither scope params provided.
        AuthorizationError (403): scope entity not owned by user.
    """
    scope_type, scope_id, _ = _resolve_scope(project_id, agent_instance_id)
    col = _scope_col(scope_type)

    client = get_supabase_client()
    await _verify_scope_ownership(scope_type, scope_id, current_user.user_id, client)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("memory_proposals")
            .select("id, proposed_content, trigger_type, conversation_id, created_at")
            .eq("user_id", current_user.user_id)
            .eq(col, scope_id)
            .eq("status", "pending")
            .execute(),
    )

    return {"proposals": result.data or []}


# ---------------------------------------------------------------------------
# Proposals — POST /api/v1/active-memory/proposals/review
# ---------------------------------------------------------------------------


@router.post("/api/v1/active-memory/proposals/review")
async def review_proposals(
    body: ReviewProposalsRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Bulk accept/reject memory proposals.

    For each accept: token cap check → insert entry + mark 'approved'. If cap exceeded, mark 'skipped_cap_exceeded'.
    For each reject: mark 'rejected'.

    Returns results array + current token_usage after all decisions.
    """
    client = get_supabase_client()
    loop = asyncio.get_running_loop()
    results = []
    # Track scope from the last resolved proposal for final token_usage computation.
    _last_scope_col: Optional[str] = None
    _last_scope_id: Optional[str] = None
    _last_cap: int = 0

    for decision in body.decisions:
        proposal_id = decision.proposal_id
        action = decision.action

        # Fetch proposal (verify ownership via user_id)
        # Default arg binds proposal_id to avoid closure capture of loop variable (S-1).
        proposal_result = await loop.run_in_executor(
            None,
            lambda _pid=proposal_id: client
                .table("memory_proposals")
                .select("id, proposed_content, project_id, agent_instance_id, user_id")
                .eq("id", _pid)
                .eq("user_id", current_user.user_id)
                .single()
                .execute(),
        )
        if not proposal_result.data:
            # Skip unknown/unauthorized proposals silently
            results.append({"proposal_id": proposal_id, "action": "skipped_not_found"})
            continue

        proposal = proposal_result.data

        # Resolve scope from proposal
        if proposal.get("project_id"):
            scope_type = "project"
            scope_id = proposal["project_id"]
            cap = ACTIVE_MEMORY_CAP_PROJECT
        else:
            scope_type = "agent_instance"
            scope_id = proposal["agent_instance_id"]
            cap = ACTIVE_MEMORY_CAP_AGENT

        col = _scope_col(scope_type)
        _last_scope_col, _last_scope_id, _last_cap = col, scope_id, cap

        if action == "reject":
            # Default arg binds proposal_id to avoid closure capture of loop variable (S-1).
            await loop.run_in_executor(
                None,
                lambda _pid=proposal_id: client
                    .table("memory_proposals")
                    .update({"status": "rejected", "reviewed_at": datetime.now(timezone.utc).isoformat()})
                    .eq("id", _pid)
                    .execute(),
            )
            results.append({"proposal_id": proposal_id, "action": "rejected"})

        elif action == "accept":
            content = proposal["proposed_content"]
            new_tokens = _count_tokens(content)
            current_tokens = await _get_current_tokens(col, scope_id, current_user.user_id, client)

            if current_tokens + new_tokens > cap:
                results.append({"proposal_id": proposal_id, "action": "skipped_cap_exceeded"})
                continue

            # Insert entry
            row = {
                "user_id": current_user.user_id,
                col: scope_id,
                "content": content,
                "source_conversation_id": proposal.get("conversation_id"),
            }
            # Default arg binds row to avoid closure capture of loop variable (S-1).
            insert_result = await loop.run_in_executor(
                None,
                lambda _row=row: client.table("active_memory_entries").insert(_row).execute(),
            )
            if not insert_result.data:
                logger.error(
                    "review_proposals: insert failed for accepted proposal",
                    extra={"proposal_id": proposal_id, "user_id": current_user.user_id},
                )
                raise ValidationError(f"Failed to insert entry for proposal {proposal_id}")

            # Mark approved. Default arg binds proposal_id (S-1).
            await loop.run_in_executor(
                None,
                lambda _pid=proposal_id: client
                    .table("memory_proposals")
                    .update({"status": "approved", "reviewed_at": datetime.now(timezone.utc).isoformat()})
                    .eq("id", _pid)
                    .execute(),
            )
            results.append({"proposal_id": proposal_id, "action": "accepted"})

    # Compute final token_usage for the scope (required by spec §4.1).
    # All decisions in a batch target the same scope — use the last resolved scope.
    if _last_scope_col and _last_scope_id:
        final_tokens = await _get_current_tokens(_last_scope_col, _last_scope_id, current_user.user_id, client)
        token_usage: dict = {"current_tokens": final_tokens, "cap_tokens": _last_cap}
    else:
        token_usage = {"current_tokens": 0, "cap_tokens": 0}

    return {"results": results, "token_usage": token_usage}


# ---------------------------------------------------------------------------
# Admin — GET /api/v1/admin/active-memory
# ---------------------------------------------------------------------------


@admin_router.get("")
async def admin_list_entries(
    user_id: str = Query(...),
    project_id: Optional[str] = Query(default=None),
    agent_instance_id: Optional[str] = Query(default=None),
    _admin: CurrentUser = Depends(require_admin),
) -> dict:
    """
    Admin endpoint: read any user's Active Memory entries for a scope.

    No ownership check — admin bypasses user scoping.

    Raises:
        ValidationError (400): both or neither scope params provided.
    """
    scope_type, scope_id, cap = _resolve_scope(project_id, agent_instance_id)
    col = _scope_col(scope_type)

    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("active_memory_entries")
            .select("id, content, source_conversation_id, created_at, updated_at")
            .eq(col, scope_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute(),
    )
    entries = result.data or []
    current_tokens = sum(_count_tokens(e["content"]) for e in entries)

    return {
        "entries": entries,
        "token_usage": {"current_tokens": current_tokens, "cap_tokens": cap},
    }
