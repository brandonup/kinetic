"""
Admin: User management — KIN-264.

Schema ref: docs/db-schema-spec.md §1 (users)
Admin-only endpoints for user list, disable, enable.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.dependencies import require_admin
from app.auth import CurrentUser
from app.core.errors import ForbiddenError, NotFoundError
from app.db import get_supabase_client

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DisableUserRequest(BaseModel):
    disabled: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


async def _get_user(supabase: Any, user_id: str) -> dict:
    result = await _run(
        lambda: supabase.table("users")
        .select("id, name, email, role, disabled_at, created_at")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise NotFoundError("User not found")
    return result.data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_users(
    _admin: CurrentUser = Depends(require_admin),
) -> list:
    supabase = get_supabase_client()
    result = await _run(
        lambda: supabase.table("users")
        .select("id, name, email, role, disabled_at, created_at")
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


@router.get("/{user_id}")
async def get_user(
    user_id: UUID,
    _admin: CurrentUser = Depends(require_admin),
) -> dict:
    supabase = get_supabase_client()
    return await _get_user(supabase, str(user_id))


@router.patch("/{user_id}/disable")
async def toggle_disable(
    user_id: UUID,
    body: DisableUserRequest,
    admin: CurrentUser = Depends(require_admin),
) -> dict:
    supabase = get_supabase_client()
    uid = str(user_id)

    if uid == admin.id:
        raise ForbiddenError("Admins cannot disable themselves")

    user = await _get_user(supabase, uid)

    import datetime
    updates: dict = {
        "disabled_at": datetime.datetime.utcnow().isoformat() if body.disabled else None
    }

    result = await _run(
        lambda: supabase.table("users").update(updates).eq("id", uid).execute()
    )
    if not result.data:
        raise NotFoundError("User not found")
    return result.data[0]
