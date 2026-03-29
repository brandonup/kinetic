"""
Knowledge Base management routes — KIN-345.

Endpoints:
  GET    /api/v1/knowledge-bases/{kb_id}/documents    — list documents (with folder/tag filter)
  GET    /api/v1/knowledge-bases/{kb_id}/folders       — list folders
  POST   /api/v1/knowledge-bases/{kb_id}/folders       — create folder
  PATCH  /api/v1/knowledge-bases/{kb_id}/folders/{id}  — rename folder
  DELETE /api/v1/knowledge-bases/{kb_id}/folders/{id}  — delete folder (reassign docs)
  PATCH  /api/v1/documents/{doc_id}/tags               — update document tags

Schema ref: db-schema-spec.md §11 (knowledge_base_folders), §12 (knowledge_base_documents)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user
from app.core.config import settings
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["kb-management"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class FolderResponse(BaseModel):
    id: str
    knowledge_base_id: str
    name: str
    created_at: str


class CreateFolderRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Folder name must not be empty")
        return v.strip()


class RenameFolderRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Folder name must not be empty")
        return v.strip()


class UpdateTagsRequest(BaseModel):
    tags: list[str]

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, v: list[str]) -> list[str]:
        return [t.strip() for t in v if t.strip()]


class DocumentListItem(BaseModel):
    id: str
    title: str
    file_type: str | None = None
    status: str
    folder_id: str | None = None
    tags: list[str] = []
    file_size_bytes: int | None = None
    created_at: str


class DeleteAllDocumentsResponse(BaseModel):
    knowledge_base_id: str
    deleted_count: int


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _verify_kb_ownership(client, kb_id: str, user_id: str) -> None:
    """Verify KB belongs to the current user. Raises 404 if not found/not owned."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_bases")
        .select("id, user_id")
        .eq("id", kb_id)
        .single()
        .execute(),
    )
    if not result.data or result.data.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")


async def _verify_doc_ownership(client, doc_id: str, user_id: str) -> dict:
    """Verify document belongs to the current user via KB chain. Returns doc row."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_base_documents")
        .select("id, knowledge_base_id, tags")
        .eq("id", doc_id)
        .is_("deleted_at", "null")
        .single()
        .execute(),
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    kb_check = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_bases")
        .select("user_id")
        .eq("id", result.data["knowledge_base_id"])
        .single()
        .execute(),
    )
    if not kb_check.data or kb_check.data.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Document not found.")

    return result.data


# ---------------------------------------------------------------------------
# Document list
# ---------------------------------------------------------------------------


@router.get("/api/v1/knowledge-bases/{kb_id}/documents")
async def list_documents(
    kb_id: UUID,
    folder_id: Optional[str] = Query(None, description="Filter by folder ID"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """List documents in a KB with optional folder/tag filters."""
    client = get_supabase()
    loop = asyncio.get_running_loop()
    await _verify_kb_ownership(client, str(kb_id), current_user.user_id)

    query = (
        client.table("knowledge_base_documents")
        .select("id, title, file_type, status, folder_id, tags, file_size_bytes, created_at")
        .eq("knowledge_base_id", str(kb_id))
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
    )

    if folder_id:
        query = query.eq("folder_id", folder_id)

    if tag:
        query = query.contains("tags", [tag])

    result = await loop.run_in_executor(None, lambda: query.execute())
    documents = result.data or []

    return {"documents": documents}


@router.delete(
    "/api/v1/knowledge-bases/{kb_id}/documents",
    response_model=DeleteAllDocumentsResponse,
)
async def delete_all_documents(
    kb_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> DeleteAllDocumentsResponse:
    """
    Hard-delete all documents in a KB.

    Chunks are removed automatically via ON DELETE CASCADE.
    Storage files are cleaned eagerly (non-fatal).
    Rejects if any document is actively ingesting (409).
    """
    from app.core.constants import ACTIVE_INGESTION_STATUSES

    client = get_supabase()
    loop = asyncio.get_running_loop()
    await _verify_kb_ownership(client, str(kb_id), current_user.user_id)

    # Fetch all non-deleted documents
    docs_result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_base_documents")
        .select("id, status, storage_uri")
        .eq("knowledge_base_id", str(kb_id))
        .is_("deleted_at", "null")
        .execute(),
    )
    documents = docs_result.data or []

    if not documents:
        return DeleteAllDocumentsResponse(
            knowledge_base_id=str(kb_id), deleted_count=0
        )

    # Guard: reject if any document is actively ingesting
    active_docs = [d for d in documents if d["status"] in ACTIVE_INGESTION_STATUSES]
    if active_docs:
        active_ids = [d["id"] for d in active_docs]
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete all: {len(active_ids)} document(s) are still processing ({', '.join(active_ids[:5])}). Wait for them to complete or fail.",
        )

    # Collect storage paths before soft-delete
    storage_paths: list[str] = []
    for d in documents:
        doc_id = d["id"]
        if d.get("storage_uri"):
            storage_paths.append(d["storage_uri"])
        storage_paths.append(f"{doc_id}/extracted.txt")

    # Hard-delete all documents — scope matches pre-flight fetch (same deleted_at filter)
    # Chunks removed automatically via ON DELETE CASCADE
    delete_result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_base_documents")
        .delete()
        .eq("knowledge_base_id", str(kb_id))
        .is_("deleted_at", "null")
        .execute(),
    )
    deleted_count = len(delete_result.data) if delete_result.data else 0

    if deleted_count == 0:
        logger.error("delete_all_documents: no rows deleted for KB %s — possible race condition", kb_id)
        raise HTTPException(
            status_code=500,
            detail="Unexpected state: documents were not found at delete time (possible race condition).",
        )

    # Eager storage cleanup (non-fatal) — will be handled by cleanup job once it exists
    for path in storage_paths:
        try:
            await loop.run_in_executor(
                None,
                lambda p=path: client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([p]),
            )
        except Exception as exc:
            logger.warning("Storage cleanup failed for %s (non-fatal): %s", path, exc)

    return DeleteAllDocumentsResponse(
        knowledge_base_id=str(kb_id), deleted_count=deleted_count
    )


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


@router.get("/api/v1/knowledge-bases/{kb_id}/folders")
async def list_folders(
    kb_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """List all folders in a KB."""
    client = get_supabase()
    loop = asyncio.get_running_loop()
    await _verify_kb_ownership(client, str(kb_id), current_user.user_id)

    result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_base_folders")
        .select("id, knowledge_base_id, name, created_at")
        .eq("knowledge_base_id", str(kb_id))
        .order("name")
        .execute(),
    )
    return {"folders": result.data or []}


@router.post("/api/v1/knowledge-bases/{kb_id}/folders", status_code=201)
async def create_folder(
    kb_id: UUID,
    body: CreateFolderRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> FolderResponse:
    """Create a new folder in a KB. MVP: flat folders only (parent_folder_id always null)."""
    client = get_supabase()
    loop = asyncio.get_running_loop()
    await _verify_kb_ownership(client, str(kb_id), current_user.user_id)

    result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_base_folders")
        .insert({"knowledge_base_id": str(kb_id), "name": body.name})
        .execute(),
    )
    if not result.data:
        logger.error("Failed to create folder in KB %s", kb_id)
        raise HTTPException(status_code=500, detail="Failed to create folder.")

    row = result.data[0]
    return FolderResponse(
        id=row["id"],
        knowledge_base_id=row["knowledge_base_id"],
        name=row["name"],
        created_at=row["created_at"],
    )


@router.patch("/api/v1/knowledge-bases/{kb_id}/folders/{folder_id}")
async def rename_folder(
    kb_id: UUID,
    folder_id: UUID,
    body: RenameFolderRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> FolderResponse:
    """Rename a folder."""
    client = get_supabase()
    loop = asyncio.get_running_loop()
    await _verify_kb_ownership(client, str(kb_id), current_user.user_id)

    result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_base_folders")
        .update({"name": body.name})
        .eq("id", str(folder_id))
        .eq("knowledge_base_id", str(kb_id))
        .execute(),
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Folder not found.")

    row = result.data[0]
    return FolderResponse(
        id=row["id"],
        knowledge_base_id=row["knowledge_base_id"],
        name=row["name"],
        created_at=row["created_at"],
    )


@router.delete("/api/v1/knowledge-bases/{kb_id}/folders/{folder_id}", status_code=200)
async def delete_folder(
    kb_id: UUID,
    folder_id: UUID,
    reassign_to: Optional[str] = Query(
        None, description="Folder ID to reassign documents to. Null = unassign."
    ),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Delete a folder. Documents in the folder are reassigned to `reassign_to`
    (another folder ID) or unassigned (folder_id set to null) if not specified.
    """
    client = get_supabase()
    loop = asyncio.get_running_loop()
    await _verify_kb_ownership(client, str(kb_id), current_user.user_id)

    # Verify folder exists in this KB
    folder_check = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_base_folders")
        .select("id")
        .eq("id", str(folder_id))
        .eq("knowledge_base_id", str(kb_id))
        .single()
        .execute(),
    )
    if not folder_check.data:
        raise HTTPException(status_code=404, detail="Folder not found.")

    # Validate reassign_to target belongs to the same KB (C1 — cross-tenant prevention)
    new_folder_id = reassign_to if reassign_to else None
    if new_folder_id:
        target_check = await loop.run_in_executor(
            None,
            lambda: client.table("knowledge_base_folders")
            .select("id")
            .eq("id", new_folder_id)
            .eq("knowledge_base_id", str(kb_id))
            .single()
            .execute(),
        )
        if not target_check.data:
            raise HTTPException(status_code=400, detail="Target folder not found in this knowledge base.")

    if new_folder_id:
        # Reassign documents to target folder before deleting this folder
        reassign_res = await loop.run_in_executor(
            None,
            lambda: client.table("knowledge_base_documents")
            .update({"folder_id": new_folder_id})
            .eq("folder_id", str(folder_id))
            .execute(),
        )
        # Supabase UPDATE returns data=[] if no matching rows — acceptable (folder may be empty).
        # An actual error would raise an exception from the client, not return silently.
        if reassign_res.data is None:
            logger.error("delete_folder: document reassignment returned None for folder %s", folder_id)
            raise HTTPException(status_code=500, detail="Failed to reassign documents.")
    else:
        # No target folder — fetch docs to guard against active ingestion, then hard-delete
        from app.core.constants import ACTIVE_INGESTION_STATUSES

        folder_docs_result = await loop.run_in_executor(
            None,
            lambda: client.table("knowledge_base_documents")
            .select("id, status")
            .eq("folder_id", str(folder_id))
            .is_("deleted_at", "null")
            .execute(),
        )
        folder_docs = folder_docs_result.data or []

        active_docs = [d for d in folder_docs if d["status"] in ACTIVE_INGESTION_STATUSES]
        if active_docs:
            active_ids = [d["id"] for d in active_docs]
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete folder: {len(active_ids)} document(s) are still processing ({', '.join(active_ids[:5])}). Wait for them to complete or fail.",
            )

        # Hard-delete — chunks cascade via ON DELETE CASCADE
        delete_docs_res = await loop.run_in_executor(
            None,
            lambda: client.table("knowledge_base_documents")
            .delete()
            .eq("folder_id", str(folder_id))
            .execute(),
        )
        if delete_docs_res.data is None:
            logger.error("delete_folder: document deletion returned None for folder %s", folder_id)
            raise HTTPException(status_code=500, detail="Failed to delete documents.")

    # Delete the folder
    await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_base_folders")
        .delete()
        .eq("id", str(folder_id))
        .execute(),
    )

    return {"status": "deleted", "reassigned_to": new_folder_id}


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


@router.patch("/api/v1/documents/{document_id}/tags")
async def update_document_tags(
    document_id: UUID,
    body: UpdateTagsRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Update tags on a document. Replaces the full tag list."""
    client = get_supabase()
    loop = asyncio.get_running_loop()
    await _verify_doc_ownership(client, str(document_id), current_user.user_id)

    result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_base_documents")
        .update({"tags": body.tags})
        .eq("id", str(document_id))
        .execute(),
    )
    if not result.data:
        logger.error("Failed to update tags for document %s", document_id)
        raise HTTPException(status_code=500, detail="Failed to update tags.")

    return {"document_id": str(document_id), "tags": body.tags}
