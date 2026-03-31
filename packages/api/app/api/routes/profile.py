"""
User Profile API routes — KIN-261.

Endpoints:
  GET  /api/v1/profile                     — fetch current user's profile
  PATCH /api/v1/profile                    — update name / bio
  GET  /api/v1/profile/api-keys            — list API key hints (never ciphertext)
  POST /api/v1/profile/api-keys            — add/update an API key (encrypts before storage)
  DELETE /api/v1/profile/api-keys/{prov}   — hard-delete an API key
  PATCH /api/v1/profile/default-model      — set default LLM generation model

Schema ref: docs/db-schema-spec.md §1 (users), §2 (user_api_keys), §19 (llm_models)
Encryption: docs/api-key-encryption-spec.md
Conventions: all Supabase calls in async def use run_in_executor (conventions.md § Supabase in Async Code)
Error handling: raise AppException subclasses — never return None/[]/False on write ops
"""

import asyncio
import logging
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user
from app.core.errors import NotFoundError, ValidationError
from app.db.supabase_client import get_supabase
from app.services.encryption import encrypt_api_key, load_master_key, mask_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

VALID_PROVIDERS = {"anthropic", "openai", "google", "groq"}


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None

    @field_validator("bio")
    @classmethod
    def bio_max_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 1000:
            raise ValueError("Bio must not exceed 1000 characters")
        return v


class UpsertApiKeyRequest(BaseModel):
    provider: str
    api_key: str

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in VALID_PROVIDERS:
            raise ValueError(f"provider must be one of {sorted(VALID_PROVIDERS)}")
        return v


class SetDefaultModelRequest(BaseModel):
    model_id: str


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
async def get_profile(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Return the current user's profile.

    Returns: id, name, bio, default_model_id. Never returns ciphertext or nonce.

    Raises:
        NotFoundError (404): User row not found in public.users.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("users")
            .select("id, name, email, bio, default_model_id")
            .eq("id", current_user.user_id)
            .single()
            .execute(),
    )
    if not result.data:
        raise NotFoundError("User profile not found")
    return result.data


@router.patch("")
async def update_profile(
    body: UpdateProfileRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update the current user's name and/or bio.

    Raises:
        ValidationError (400): bio exceeds 1000 characters (caught by Pydantic validator).
    """
    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.bio is not None:
        updates["bio"] = body.bio

    if not updates:
        # Nothing to update — return current profile
        loop = asyncio.get_running_loop()
        client = get_supabase_client()
        result = await loop.run_in_executor(
            None,
            lambda: client
                .table("users")
                .select("id, name, email, bio, default_model_id")
                .eq("id", current_user.user_id)
                .single()
                .execute(),
        )
        if not result.data:
            raise NotFoundError("User profile not found")
        return result.data

    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("users")
            .update(updates)
            .eq("id", current_user.user_id)
            .execute(),
    )
    if not result.data:
        raise NotFoundError("User profile not found")
    return result.data[0]


@router.get("/api-keys")
async def list_api_keys(
    current_user: CurrentUser = Depends(get_current_user),
) -> list:
    """
    List the current user's configured API key hints.

    Returns: provider, key_hint, validated_at for each configured provider.
    NEVER returns key_ciphertext or key_nonce.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("user_api_keys")
            .select("provider, key_hint, validated_at")
            .eq("user_id", current_user.user_id)
            .execute(),
    )
    # Read-path: return empty list on no results (fail-open documented)
    return result.data or []


@router.post("/api-keys")
async def upsert_api_key(
    body: UpsertApiKeyRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Add or update an API key for a provider.

    Encrypts the plaintext key with AES-256-GCM before storage.
    Returns only the key_hint — never the plaintext or ciphertext.

    Schema ref: docs/db-schema-spec.md §2 (user_api_keys columns)

    Raises:
        ValidationError (422): invalid provider (Pydantic).
    """
    master_key = load_master_key()
    key_hint = mask_api_key(body.api_key)
    ciphertext, nonce = encrypt_api_key(body.api_key, master_key, current_user.user_id)

    row = {
        "user_id": current_user.user_id,
        "provider": body.provider,
        "key_ciphertext": "\\x" + ciphertext.hex(),  # \x prefix tells PostgREST to decode as binary hex
        "key_nonce": "\\x" + nonce.hex(),
        "key_hint": key_hint,
    }

    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("user_api_keys")
            .upsert(row, on_conflict="user_id,provider")
            .execute(),
    )
    if not result.data:
        logger.error(
            "upsert_api_key: no data returned from upsert",
            extra={"user_id": current_user.user_id, "provider": body.provider},
        )
        raise ValidationError("Failed to save API key")

    # Return only safe fields — never ciphertext or nonce
    return {"provider": body.provider, "key_hint": key_hint}


@router.delete("/api-keys/{provider}", status_code=204)
async def delete_api_key(
    provider: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """
    Hard-delete an API key for a provider.

    Schema ref: docs/db-schema-spec.md §2 (user_api_keys, UNIQUE(user_id, provider))

    Raises:
        NotFoundError (404): No key found for this provider.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("user_api_keys")
            .delete()
            .eq("user_id", current_user.user_id)
            .eq("provider", provider)
            .execute(),
    )
    if not result.data:
        raise NotFoundError(f"No API key found for provider: {provider}")


@router.patch("/default-model")
async def set_default_model(
    body: SetDefaultModelRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Set the user's default LLM generation model.

    Validates that the model exists, is enabled, and is category='generation'.

    Schema ref:
      - docs/db-schema-spec.md §1 (users.default_model_id)
      - docs/db-schema-spec.md §19 (llm_models: id, enabled, category)

    Raises:
        NotFoundError (404): Model not found, disabled, or not a generation model.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Verify model exists, is enabled, and is a generation model
    model_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("llm_models")
            .select("id, enabled, category")
            .eq("id", body.model_id)
            .single()
            .execute(),
    )
    model = model_result.data
    if not model or not model.get("enabled") or model.get("category") != "generation":
        raise NotFoundError(
            "Model not found or not available for selection. "
            "Model must be an enabled generation model."
        )

    # Update user's default model
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("users")
            .update({"default_model_id": body.model_id})
            .eq("id", current_user.user_id)
            .execute(),
    )
    if not result.data:
        raise NotFoundError("User profile not found")

    return {"default_model_id": body.model_id}
