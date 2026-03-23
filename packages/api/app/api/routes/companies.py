"""
Company CRUD — KIN-262.

Schema ref: docs/db-schema-spec.md §3 (companies)
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator

from app.auth import CurrentUser, get_current_user
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.db import get_supabase_client

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateCompanyRequest(BaseModel):
    name: str
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 1000:
            raise ValueError("description must be 1000 characters or fewer")
        return v


class UpdateCompanyRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    @field_validator("description")
    @classmethod
    def description_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 1000:
            raise ValueError("description must be 1000 characters or fewer")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


async def _get_owned_company(supabase: Any, company_id: str, user_id: str) -> dict:
    result = await _run(
        lambda: supabase.table("companies")
        .select("*")
        .eq("id", company_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise NotFoundError("Company not found")
    return result.data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CreateCompanyRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    row = {
        "user_id": current_user.id,
        "name": body.name,
        "description": body.description,
    }
    result = await _run(lambda: supabase.table("companies").insert(row).execute())
    if not result.data:
        raise ValidationError("Failed to create company")
    return result.data[0]


@router.get("")
async def list_companies(
    current_user: CurrentUser = Depends(get_current_user),
) -> list:
    supabase = get_supabase_client()
    result = await _run(
        lambda: supabase.table("companies")
        .select("*")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.get("/{company_id}")
async def get_company(
    company_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    return await _get_owned_company(supabase, str(company_id), current_user.id)


@router.patch("/{company_id}")
async def update_company(
    company_id: UUID,
    body: UpdateCompanyRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    cid = str(company_id)
    await _get_owned_company(supabase, cid, current_user.id)

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if not updates:
        return await _get_owned_company(supabase, cid, current_user.id)

    result = await _run(
        lambda: supabase.table("companies")
        .update(updates)
        .eq("id", cid)
        .eq("user_id", current_user.id)
        .execute()
    )
    if not result.data:
        raise NotFoundError("Company not found")
    return result.data[0]


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_company(
    company_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    supabase = get_supabase_client()
    cid = str(company_id)
    await _get_owned_company(supabase, cid, current_user.id)
    await _run(
        lambda: supabase.table("companies")
        .delete()
        .eq("id", cid)
        .eq("user_id", current_user.id)
        .execute()
    )
