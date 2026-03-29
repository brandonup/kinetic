"""
MCP Token management routes — KIN-325.

Endpoints:
  POST  /api/v1/mcp/tokens              — generate a new bearer token (raw value returned once)
  GET   /api/v1/mcp/tokens              — list active tokens (hash never exposed)
  PATCH /api/v1/mcp/tokens/{id}/revoke  — revoke a token

Token storage: SHA-256 hash per ADR-006 §1 (overrides db-schema-spec §18 which says bcrypt).
Token format: raw = os.urandom(32).hex() (64 chars); stored as sha256(raw); returned as "mcp_{raw}".

Schema ref: docs/db-schema-spec.md §18 (mcp_tokens)
Conventions: all Supabase calls in async def use run_in_executor (conventions.md § Supabase in Async Code)
Error handling: raise AppException subclasses — never return None/[]/False on write ops
"""

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user
from app.core.errors import AppException, ConflictError, NotFoundError
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mcp/tokens", tags=["mcp-tokens"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CreateTokenRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name is required")
        if len(v) > 64:
            raise ValueError("name must be 64 characters or fewer")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_supabase_client():
    """Return the service-role Supabase client. Module-level so tests can patch it."""
    return get_supabase()


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash for MCP bearer token storage. Per ADR-006 §1."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("")
async def create_token(
    body: CreateTokenRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Generate a new MCP bearer token.

    The raw token is returned exactly once in this response.
    Subsequent GET requests return only masked metadata — the raw value is gone.

    Returns: id, name, token ("mcp_<hex>"), created_at
    Raises:
        ValidationError (400): name empty or exceeds 64 chars (Pydantic validator).
    """
    raw = os.urandom(32).hex()
    token_hash = _hash_token(raw)

    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("mcp_tokens")
            .insert({
                "user_id": current_user.user_id,
                "token_hash": token_hash,
                "name": body.name,
            })
            .execute(),
    )
    if not result.data:
        raise AppException("INTERNAL_ERROR", "Failed to create MCP token")

    row = result.data[0]
    return {
        "id": row["id"],
        "name": row["name"],
        "token": f"mcp_{raw}",
        "created_at": row["created_at"],
    }


@router.get("")
async def list_tokens(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List the current user's active (non-revoked) MCP tokens.

    Returns: { "tokens": [{ id, name, last_used_at, created_at }] }
    token_hash is never included in the response.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("mcp_tokens")
            .select("id, name, last_used_at, created_at")
            .eq("user_id", current_user.user_id)
            .is_("revoked_at", "null")
            .order("created_at", desc=False)
            .execute(),
    )
    return {"tokens": result.data or []}


@router.patch("/{token_id}/revoke")
async def revoke_token(
    token_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Revoke an MCP token. Clients using this token immediately lose access.

    Returns: { id, revoked_at }
    Raises:
        NotFoundError (404): token not found or belongs to a different user.
        ConflictError (409): token is already revoked.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Fetch to verify ownership and current state
    fetch_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("mcp_tokens")
            .select("id, revoked_at")
            .eq("id", token_id)
            .eq("user_id", current_user.user_id)
            .single()
            .execute(),
    )
    if not fetch_result.data:
        raise NotFoundError("MCP token not found")

    if fetch_result.data.get("revoked_at") is not None:
        raise ConflictError("Token is already revoked")

    # Revoke
    update_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("mcp_tokens")
            .update({"revoked_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", token_id)
            .eq("user_id", current_user.user_id)
            .execute(),
    )
    if not update_result.data:
        raise AppException("INTERNAL_ERROR", "Failed to revoke MCP token")

    row = update_result.data[0]
    return {"id": row["id"], "revoked_at": row["revoked_at"]}
