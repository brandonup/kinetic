"""
Admin: LLM Model management — KIN-265.

Schema ref: docs/db-schema-spec.md §19 (llm_models)
Admin-only endpoints for managing the model library.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator

from app.dependencies import require_admin
from app.auth import CurrentUser
from app.core.errors import NotFoundError, ValidationError
from app.db import get_supabase_client

router = APIRouter(prefix="/api/v1/admin/models", tags=["admin-models"])

VALID_CATEGORIES = {"generation", "embedding", "reranking"}
VALID_PROVIDERS = {"anthropic", "openai", "google", "groq"}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateModelRequest(BaseModel):
    provider: str
    model_id: str
    display_name: str
    category: str
    enabled: bool = True
    context_window: Optional[int] = None

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {VALID_CATEGORIES}")
        return v


class UpdateModelRequest(BaseModel):
    display_name: Optional[str] = None
    enabled: Optional[bool] = None
    context_window: Optional[int] = None


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
async def list_models(
    category: Optional[str] = None,
    _admin: CurrentUser = Depends(require_admin),
) -> list:
    supabase = get_supabase_client()
    query = supabase.table("llm_models").select("*").order("created_at", desc=False)
    if category:
        query = query.eq("category", category)
    result = await _run(lambda: query.execute())
    return result.data or []


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_model(
    body: CreateModelRequest,
    _admin: CurrentUser = Depends(require_admin),
) -> dict:
    supabase = get_supabase_client()
    row = {
        "provider": body.provider,
        "model_id": body.model_id,
        "display_name": body.display_name,
        "category": body.category,
        "enabled": body.enabled,
        "context_window": body.context_window,
    }
    result = await _run(lambda: supabase.table("llm_models").insert(row).execute())
    if not result.data:
        raise ValidationError("Failed to create model")
    return result.data[0]


@router.patch("/{model_id}")
async def update_model(
    model_id: UUID,
    body: UpdateModelRequest,
    _admin: CurrentUser = Depends(require_admin),
) -> dict:
    supabase = get_supabase_client()
    mid = str(model_id)

    existing = await _run(
        lambda: supabase.table("llm_models")
        .select("id")
        .eq("id", mid)
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise NotFoundError("Model not found")

    updates: dict = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if body.context_window is not None:
        updates["context_window"] = body.context_window

    if not updates:
        result = await _run(
            lambda: supabase.table("llm_models")
            .select("*")
            .eq("id", mid)
            .maybe_single()
            .execute()
        )
        return result.data or {}

    result = await _run(
        lambda: supabase.table("llm_models").update(updates).eq("id", mid).execute()
    )
    return result.data[0] if result.data else {}


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_model(
    model_id: UUID,
    _admin: CurrentUser = Depends(require_admin),
) -> None:
    supabase = get_supabase_client()
    mid = str(model_id)
    existing = await _run(
        lambda: supabase.table("llm_models")
        .select("id")
        .eq("id", mid)
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise NotFoundError("Model not found")
    await _run(
        lambda: supabase.table("llm_models").delete().eq("id", mid).execute()
    )
