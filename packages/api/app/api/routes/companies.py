"""
Company API routes — KIN-262.

Endpoints:
  POST   /api/v1/companies                  — create a company
  GET    /api/v1/companies                  — list user's companies (ordered by updated_at DESC)
  GET    /api/v1/companies/{company_id}     — get a single company
  PATCH  /api/v1/companies/{company_id}     — update name / description
  DELETE /api/v1/companies/{company_id}     — hard-delete (cascade via FK to projects/conversations)

Schema ref: docs/db-schema-spec.md §3 (companies)
Conventions: all Supabase calls in async def use run_in_executor (conventions.md § Supabase in Async Code)
Error handling: raise AppException subclasses — never return None/[]/False on write ops
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user
from app.core.errors import NotFoundError, ValidationError
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CreateCompanyRequest(BaseModel):
    name: str
    description: Optional[str] = None

    @field_validator("description")
    @classmethod
    def description_max_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 1000:
            raise ValueError("Description must not exceed 1000 characters")
        return v


class UpdateCompanyRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    @field_validator("description")
    @classmethod
    def description_max_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 1000:
            raise ValueError("Description must not exceed 1000 characters")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_supabase_client():
    """Return the service-role Supabase client. Defined as a module-level function so tests can patch it."""
    return get_supabase()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("")
async def create_company(
    body: CreateCompanyRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Create a new company owned by the current user.

    Raises:
        ValidationError (400): DB returned no data after insert.
    """
    row = {
        "user_id": current_user.user_id,
        "name": body.name,
        "description": body.description,
    }

    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client.table("companies").insert(row).execute(),
    )
    if not result.data:
        logger.error(
            "create_company: no data returned from insert",
            extra={"user_id": current_user.user_id},
        )
        raise ValidationError("Failed to create company")
    return result.data[0]


@router.get("")
async def list_companies(
    current_user: CurrentUser = Depends(get_current_user),
) -> list:
    """
    List the current user's companies, ordered by most-recently-updated first.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("companies")
            .select("id, user_id, name, description, created_at, updated_at")
            .eq("user_id", current_user.user_id)
            .order("updated_at", desc=True)
            .execute(),
    )
    return result.data or []


@router.get("/{company_id}")
async def get_company(
    company_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Get a single company by ID.

    Raises:
        NotFoundError (404): Company not found or not owned by current user.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("companies")
            .select("id, user_id, name, description, created_at, updated_at")
            .eq("id", company_id)
            .eq("user_id", current_user.user_id)
            .single()
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Company not found")
    return result.data


@router.patch("/{company_id}")
async def update_company(
    company_id: str,
    body: UpdateCompanyRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update a company's name and/or description.

    Raises:
        NotFoundError (404): Company not found or not owned by current user.
    """
    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description

    # Always bump updated_at on explicit PATCH
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("companies")
            .update(updates)
            .eq("id", company_id)
            .eq("user_id", current_user.user_id)
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Company not found")
    return result.data[0]


@router.delete("/{company_id}", status_code=204)
async def delete_company(
    company_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """
    Hard-delete a company. Cascades to projects, conversations, and related data via FK ON DELETE CASCADE.

    Raises:
        NotFoundError (404): Company not found or not owned by current user.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("companies")
            .delete()
            .eq("id", company_id)
            .eq("user_id", current_user.user_id)
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Company not found")
