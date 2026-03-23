"""
User profile CRUD — KIN-261.

Schema ref: docs/db-schema-spec.md §1 (users), §2 (user_api_keys)
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator

from app.auth import CurrentUser, get_current_user
from app.core.errors import NotFoundError, ValidationError
from app.db import get_supabase_client

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])

VALID_PROVIDERS = {"anthropic", "openai", "google", "groq"}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    default_model_id: Optional[UUID] = None

    @field_validator("bio")
    @classmethod
    def bio_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 1000:
            raise ValueError("bio must be 1000 characters or fewer")
        return v


class UpsertApiKeyRequest(BaseModel):
    provider: str
    key: str

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, v: str) -> str:
        if v not in VALID_PROVIDERS:
            raise ValueError(f"provider must be one of {VALID_PROVIDERS}")
        return v

    @field_validator("key")
    @classmethod
    def key_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("key must not be empty")
        return v.strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def get_profile(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    result = await _run(
        lambda: supabase.table("users")
        .select("id, name, bio, role, default_model_id, active_company_id, created_at, updated_at")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise NotFoundError("User profile not found")
    return result.data


@router.patch("")
async def update_profile(
    body: UpdateProfileRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.bio is not None:
        updates["bio"] = body.bio
    if body.default_model_id is not None:
        updates["default_model_id"] = str(body.default_model_id)

    if not updates:
        result = await _run(
            lambda: supabase.table("users")
            .select("id, name, bio, role, default_model_id, active_company_id, created_at, updated_at")
            .eq("id", current_user.id)
            .maybe_single()
            .execute()
        )
        return result.data or {}

    result = await _run(
        lambda: supabase.table("users")
        .update(updates)
        .eq("id", current_user.id)
        .execute()
    )
    if not result.data:
        raise NotFoundError("User not found")
    return result.data[0]


@router.get("/api-keys")
async def list_api_keys(
    current_user: CurrentUser = Depends(get_current_user),
) -> list:
    supabase = get_supabase_client()
    result = await _run(
        lambda: supabase.table("user_api_keys")
        .select("id, provider, key_hint, validated_at, created_at")
        .eq("user_id", current_user.id)
        .execute()
    )
    return result.data or []


@router.put("/api-keys/{provider}", status_code=status.HTTP_200_OK)
async def upsert_api_key(
    provider: str,
    body: UpsertApiKeyRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Store an encrypted API key. Returns the key hint, never the plaintext."""
    supabase = get_supabase_client()

    if provider not in VALID_PROVIDERS:
        raise ValidationError(f"provider must be one of {VALID_PROVIDERS}")

    # Encrypt key
    from app.services.encryption import encrypt_key, mask_key

    ciphertext, nonce = encrypt_key(body.key)
    hint = mask_key(body.key)

    row = {
        "user_id": current_user.id,
        "provider": provider,
        "key_ciphertext": ciphertext,
        "key_nonce": nonce,
        "key_hint": hint,
    }

    # Upsert on (user_id, provider) unique constraint
    result = await _run(
        lambda: supabase.table("user_api_keys")
        .upsert(row, on_conflict="user_id,provider")
        .execute()
    )
    if not result.data:
        raise ValidationError("Failed to save API key")
    saved = result.data[0]
    # Never return ciphertext
    saved.pop("key_ciphertext", None)
    saved.pop("key_nonce", None)
    return saved


@router.delete("/api-keys/{provider}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_api_key(
    provider: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    supabase = get_supabase_client()
    await _run(
        lambda: supabase.table("user_api_keys")
        .delete()
        .eq("user_id", current_user.id)
        .eq("provider", provider)
        .execute()
    )
