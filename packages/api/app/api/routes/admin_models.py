"""
Admin LLM Models API routes — KIN-265.

Endpoints:
  GET    /api/v1/admin/models              — list all models (all authenticated users — used by profile page)
  POST   /api/v1/admin/models              — add a model (admin only, returns 201)
  PATCH  /api/v1/admin/models/{model_id}   — update model (admin only)
  DELETE /api/v1/admin/models/{model_id}   — delete model (admin only, returns 204)

Schema ref: docs/db-schema-spec.md §19 (llm_models)
Cache: In-memory module-level list. Populated on first GET. Invalidated on any write.
Admin enforcement: require_admin dependency from app.auth.deps.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user, require_admin
from app.core.errors import NotFoundError, ValidationError
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/models", tags=["admin-models"])

# ---------------------------------------------------------------------------
# In-memory model cache
# ---------------------------------------------------------------------------

_models_cache: list | None = None


def _invalidate_cache() -> None:
    global _models_cache
    _models_cache = None


def _set_cache(models: list) -> None:
    global _models_cache
    _models_cache = models


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

VALID_PROVIDERS = {"anthropic", "openai", "google", "groq"}
VALID_CATEGORIES = {"generation", "embedding", "reranking"}


class AddModelRequest(BaseModel):
    provider: str
    model_id: str
    display_name: str
    category: str
    context_window: Optional[int] = None

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in VALID_PROVIDERS:
            raise ValueError(f"provider must be one of {sorted(VALID_PROVIDERS)}")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}")
        return v


class UpdateModelRequest(BaseModel):
    display_name: Optional[str] = None
    enabled: Optional[bool] = None
    context_window: Optional[int] = None


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
async def list_models(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List all LLM models.

    Accessible to all authenticated users — used by profile page for default model selector
    and by admin panel for model management.

    Returns from in-memory cache on subsequent calls. Cache is invalidated on any write.
    """
    global _models_cache
    if _models_cache is not None:
        return {"models": _models_cache}

    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("llm_models")
            .select("id, provider, model_id, display_name, category, enabled, context_window, created_at, updated_at")
            .order("display_name")
            .execute(),
    )
    models = result.data or []
    _set_cache(models)
    return {"models": models}


@router.post("", status_code=201)
async def add_model(
    body: AddModelRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    Add a new LLM model to the library.

    Admin only. Invalidates the model cache on success.

    Raises:
        ValidationError (400): DB returned no data after insert.
    """
    row = {
        "provider": body.provider,
        "model_id": body.model_id,
        "display_name": body.display_name,
        "category": body.category,
        "context_window": body.context_window,
        "enabled": True,
    }

    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client.table("llm_models").insert(row).execute(),
    )
    if not result.data:
        logger.error(
            "add_model: no data returned from insert",
            extra={"model_id": body.model_id, "user_id": current_user.user_id},
        )
        raise ValidationError("Failed to add model")

    _invalidate_cache()
    return result.data[0]


@router.patch("/{model_id}")
async def update_model(
    model_id: str,
    body: UpdateModelRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    Update a model's display_name, enabled status, or context_window.

    Admin only. Invalidates the model cache on success.

    Raises:
        NotFoundError (404): Model not found.
    """
    updates: dict = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if body.context_window is not None:
        updates["context_window"] = body.context_window

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("llm_models")
            .update(updates)
            .eq("id", model_id)
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Model not found")

    _invalidate_cache()
    return result.data[0]


@router.delete("/{model_id}", status_code=204)
async def delete_model(
    model_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> None:
    """
    Delete a model from the library.

    Admin only. Invalidates the model cache on success.

    Raises:
        NotFoundError (404): Model not found.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("llm_models")
            .delete()
            .eq("id", model_id)
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Model not found")

    _invalidate_cache()
