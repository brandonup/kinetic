"""
Project CRUD — KIN-263.

Schema ref: docs/db-schema-spec.md §4 (projects)
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

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    name: str
    company_id: UUID
    instructions: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    instructions: Optional[str] = None
    company_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


async def _get_owned_project(supabase: Any, project_id: str, user_id: str) -> dict:
    result = await _run(
        lambda: supabase.table("projects")
        .select("*")
        .eq("id", project_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise NotFoundError("Project not found")
    return result.data


async def _verify_company_ownership(
    supabase: Any, company_id: str, user_id: str
) -> None:
    result = await _run(
        lambda: supabase.table("companies")
        .select("id")
        .eq("id", company_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise ForbiddenError("Company not found or does not belong to you")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: CreateProjectRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    company_id = str(body.company_id)
    await _verify_company_ownership(supabase, company_id, current_user.id)

    row = {
        "user_id": current_user.id,
        "company_id": company_id,
        "name": body.name,
        "instructions": body.instructions,
    }
    result = await _run(lambda: supabase.table("projects").insert(row).execute())
    if not result.data:
        raise ValidationError("Failed to create project")
    return result.data[0]


@router.get("")
async def list_projects(
    company_id: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
) -> list:
    supabase = get_supabase_client()
    query = (
        supabase.table("projects")
        .select("*")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
    )
    if company_id:
        query = query.eq("company_id", company_id)

    result = await _run(lambda: query.execute())
    return result.data or []


@router.get("/{project_id}")
async def get_project(
    project_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    return await _get_owned_project(supabase, str(project_id), current_user.id)


@router.patch("/{project_id}")
async def update_project(
    project_id: UUID,
    body: UpdateProjectRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    pid = str(project_id)
    await _get_owned_project(supabase, pid, current_user.id)

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.instructions is not None:
        updates["instructions"] = body.instructions
    if body.company_id is not None:
        # Verify new company belongs to user
        await _verify_company_ownership(
            supabase, str(body.company_id), current_user.id
        )
        updates["company_id"] = str(body.company_id)

    if not updates:
        return await _get_owned_project(supabase, pid, current_user.id)

    result = await _run(
        lambda: supabase.table("projects")
        .update(updates)
        .eq("id", pid)
        .eq("user_id", current_user.id)
        .execute()
    )
    if not result.data:
        raise NotFoundError("Project not found")
    return result.data[0]


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_project(
    project_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    supabase = get_supabase_client()
    pid = str(project_id)
    await _get_owned_project(supabase, pid, current_user.id)
    await _run(
        lambda: supabase.table("projects")
        .delete()
        .eq("id", pid)
        .eq("user_id", current_user.id)
        .execute()
    )
