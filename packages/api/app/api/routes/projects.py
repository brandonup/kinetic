"""
Project API routes — KIN-263.

Endpoints:
  POST   /api/v1/projects                  — create a project (201)
  GET    /api/v1/projects                  — list user's projects, optional ?company_id= filter
  GET    /api/v1/projects/{project_id}     — get a single project
  PATCH  /api/v1/projects/{project_id}     — partial update (name, instructions, company_id)
  DELETE /api/v1/projects/{project_id}     — hard-delete (204)

Schema ref: docs/db-schema-spec.md §4 (projects)
Spec ref: docs/specs/kin-257-projects-conversations-spec.md §Part 1
Conventions: all Supabase calls in async def use run_in_executor
Error handling: raise AppException subclasses — never return None/[]/False on write ops
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user
from app.core.errors import AuthorizationError, NotFoundError, ValidationError
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    name: str
    company_id: str
    instructions: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must not be empty")
        return v


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    company_id: Optional[str] = None
    instructions: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("name must not be empty")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_supabase_client():
    """Return the service-role Supabase client. Defined as a module-level function so tests can patch it."""
    return get_supabase()


async def _verify_company_ownership(company_id: str, user_id: str, client) -> None:
    """
    Verify the company belongs to the requesting user.

    Raises:
        AuthorizationError (403): company does not exist or not owned by user.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("companies")
            .select("id")
            .eq("id", company_id)
            .eq("user_id", user_id)
            .single()
            .execute(),
    )
    if not result.data:
        raise AuthorizationError("Company does not belong to the requesting user")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_project(
    body: CreateProjectRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Create a new project.

    Verifies company ownership before insert. Sets user_id from auth (denormalized for RLS).

    Raises:
        AuthorizationError (403): company_id does not belong to the user.
        ValidationError (400): DB returned no data after insert.
    """
    client = get_supabase_client()
    await _verify_company_ownership(body.company_id, current_user.user_id, client)

    row = {
        "user_id": current_user.user_id,
        "company_id": body.company_id,
        "name": body.name,
        "instructions": body.instructions,
    }

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client.table("projects").insert(row).execute(),
    )
    if not result.data:
        logger.error(
            "create_project: no data returned from insert",
            extra={"user_id": current_user.user_id, "company_id": body.company_id},
        )
        raise ValidationError("Failed to create project")
    return result.data[0]


@router.get("")
async def list_projects(
    company_id: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List the current user's projects, ordered by most-recently-updated first.

    If company_id is provided, verifies the company belongs to the user and filters results.

    Raises:
        AuthorizationError (403): company_id does not belong to the user.
    """
    client = get_supabase_client()

    if company_id:
        await _verify_company_ownership(company_id, current_user.user_id, client)

    loop = asyncio.get_running_loop()

    if company_id:
        result = await loop.run_in_executor(
            None,
            lambda: client
                .table("projects")
                .select("id, company_id, user_id, name, instructions, created_at, updated_at")
                .eq("user_id", current_user.user_id)
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .execute(),
        )
    else:
        result = await loop.run_in_executor(
            None,
            lambda: client
                .table("projects")
                .select("id, company_id, user_id, name, instructions, created_at, updated_at")
                .eq("user_id", current_user.user_id)
                .order("updated_at", desc=True)
                .execute(),
        )

    return {"projects": result.data or []}


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Get a single project by ID.

    Raises:
        NotFoundError (404): Project not found or not owned by current user.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("projects")
            .select("id, company_id, user_id, name, instructions, created_at, updated_at")
            .eq("id", project_id)
            .eq("user_id", current_user.user_id)
            .single()
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Project not found")
    return result.data


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update a project's name, instructions, and/or company assignment.

    If company_id is provided, verifies the new company belongs to the user.
    On company reassignment, all child data (conversations, KB, Active Memory) stays
    attached to the project — the DB FK structure handles this automatically.

    Raises:
        AuthorizationError (403): new company_id does not belong to the user.
        NotFoundError (404): Project not found or not owned by current user.
    """
    client = get_supabase_client()

    if body.company_id is not None:
        await _verify_company_ownership(body.company_id, current_user.user_id, client)

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.company_id is not None:
        updates["company_id"] = body.company_id
    if body.instructions is not None:
        updates["instructions"] = body.instructions

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("projects")
            .update(updates)
            .eq("id", project_id)
            .eq("user_id", current_user.user_id)
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Project not found")
    return result.data[0]


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """
    Hard-delete a project. Cascades to conversations, knowledge_bases, and active_memory_entries via FK.

    Raises:
        NotFoundError (404): Project not found or not owned by current user.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("projects")
            .delete()
            .eq("id", project_id)
            .eq("user_id", current_user.user_id)
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Project not found")
