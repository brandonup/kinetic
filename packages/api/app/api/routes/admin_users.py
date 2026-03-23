"""
Admin Users API routes — KIN-264.

Endpoints:
  GET    /api/v1/admin/users                          — list all users (admin only)
  PATCH  /api/v1/admin/users/{user_id}/disable        — disable user (admin only; 409 if public agents exist)
  PATCH  /api/v1/admin/users/{user_id}/enable         — re-enable user (admin only)
  PATCH  /api/v1/admin/users/{user_id}/transfer-agent — transfer agent ownership (admin only)

Schema ref: docs/db-schema-spec.md §1 (users), §8 (agent_definitions)
Admin enforcement: require_admin dependency from app.auth.deps.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.deps import CurrentUser, require_admin
from app.core.errors import NotFoundError
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TransferAgentRequest(BaseModel):
    agent_id: str
    new_owner_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_supabase_client():
    """Return the service-role Supabase client. Defined as a module-level function so tests can patch it."""
    return get_supabase()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
async def list_users(
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    List all users.

    Merges public.users (name, role, disabled_at) with auth.users emails.
    Returns {"users": [...]}.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Fetch public.users rows
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("users")
            .select("id, name, role, disabled_at, created_at")
            .order("created_at", desc=True)
            .execute(),
    )
    rows = result.data or []

    # Fetch emails from auth.users via admin API
    try:
        auth_users = await loop.run_in_executor(
            None,
            lambda: client.auth.admin.list_users(),
        )
        email_by_id = {str(u.id): u.email for u in (auth_users or [])}
    except Exception:
        logger.warning("list_users: failed to fetch auth emails — returning empty emails")
        email_by_id = {}

    # Merge email into each row
    users = [{**row, "email": email_by_id.get(row["id"], "")} for row in rows]
    return {"users": users}


@router.patch("/{user_id}/disable", status_code=204)
async def disable_user(
    user_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> None:
    """
    Disable a user account.

    Blocked if the user owns any public agents — returns 409 with
    { "error": "transfer_required", "public_agent_ids": [...] }.

    Schema ref: docs/db-schema-spec.md §1 (users.disabled_at), §8 (agent_definitions)

    Raises:
        HTTPException (409): User owns public agents that must be transferred first.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Check for public agents owned by this user
    agents_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .select("id")
            .eq("owner_id", user_id)
            .eq("visibility", "public")
            .execute(),
    )
    if agents_result.data:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "transfer_required",
                "public_agent_ids": [row["id"] for row in agents_result.data],
            },
        )

    # Set disabled_at
    await loop.run_in_executor(
        None,
        lambda: client
            .table("users")
            .update({"disabled_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", user_id)
            .execute(),
    )


@router.patch("/{user_id}/enable")
async def enable_user(
    user_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    Re-enable a disabled user account.

    Schema ref: docs/db-schema-spec.md §1 (users.disabled_at)

    Raises:
        NotFoundError (404): User not found.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("users")
            .update({"disabled_at": None})
            .eq("id", user_id)
            .execute(),
    )
    if not result.data:
        raise NotFoundError("User not found")
    return result.data[0]


@router.patch("/{user_id}/transfer-agent")
async def transfer_agent(
    user_id: str,
    body: TransferAgentRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    Transfer ownership of an agent to another user.

    Schema ref: docs/db-schema-spec.md §8 (agent_definitions.owner_id)

    Raises:
        NotFoundError (404): Agent not found.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("agent_definitions")
            .update({"owner_id": body.new_owner_id})
            .eq("id", body.agent_id)
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Agent not found")
    return result.data[0]
