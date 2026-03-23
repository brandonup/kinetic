"""
Document upload endpoint.

POST /api/v1/documents/upload
  - Validates file size (25 MB limit) at the API boundary
  - Creates knowledge_base_documents row with status='pending'
  - Dispatches ingestion pipeline via TaskDispatcher (background)
  - Returns {document_id, status} immediately

GET /api/v1/documents/{document_id}
  - Returns current document status (for polling / retry UX)

Schema ref: db-schema-spec.md §12 (knowledge_base_documents)
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth.deps import CurrentUser, get_current_user
from app.db.supabase_client import get_supabase
from app.services.background import TaskDispatcher
from app.services.ingestion.pipeline import run_ingestion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024  # 25 MB


class UploadResponse(BaseModel):
    document_id: str
    status: str


class DocumentStatusResponse(BaseModel):
    document_id: str
    status: str
    error_stage: str | None = None
    error_message: str | None = None
    retry_count: int = 0


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    knowledge_base_id: UUID = Form(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> UploadResponse:
    """
    Upload a document to a Knowledge Base and start background ingestion.

    Validates file size at the boundary (413 if > 25 MB).
    Creates a knowledge_base_documents row immediately and returns.
    Ingestion runs in the background: pending → extracting → chunking → embedding → completed.
    """
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds 25 MB upload limit ({len(content):,} bytes received).",
        )

    supabase = get_supabase()
    loop = asyncio.get_running_loop()

    # Resolve scope columns from the parent knowledge_base
    kb_result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_bases")
        .select("project_id, agent_definition_id, user_id")
        .eq("id", str(knowledge_base_id))
        .single()
        .execute(),
    )
    if not kb_result.data:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")

    kb = kb_result.data
    # RLS: only the KB owner can upload to it
    if kb.get("user_id") != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    project_id = UUID(kb["project_id"]) if kb.get("project_id") else None
    agent_definition_id = UUID(kb["agent_definition_id"]) if kb.get("agent_definition_id") else None

    document_id = uuid4()
    content_type = file.content_type or "application/octet-stream"

    # Create document row with status=pending
    insert_result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents")
        .insert(
            {
                "id": str(document_id),
                "knowledge_base_id": str(knowledge_base_id),
                "title": file.filename or "Untitled",
                "file_type": content_type,
                "file_size_bytes": len(content),
                "status": "pending",
                "retry_count": 0,
            }
        )
        .execute(),
    )
    if not insert_result.data:
        raise RuntimeError(f"Failed to create document row for {document_id}")

    # Dispatch ingestion pipeline to background
    # FastAPI BackgroundTasks.add_task handles async callables natively — pass the
    # coroutine function (not asyncio.run) so it is awaited in the existing event loop.
    dispatcher = TaskDispatcher(background_tasks)
    dispatcher.dispatch(
        run_ingestion,
        supabase,
        document_id,
        knowledge_base_id,
        project_id,
        agent_definition_id,
        content,
        file.filename or "",
        content_type,
    )

    return UploadResponse(document_id=str(document_id), status="pending")


@router.get("/{document_id}", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentStatusResponse:
    """Return current ingestion status for a document."""
    supabase = get_supabase()
    loop = asyncio.get_running_loop()

    result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents")
        .select("id, status, error_stage, error_message, retry_count, knowledge_base_id")
        .eq("id", str(document_id))
        .is_("deleted_at", "null")
        .single()
        .execute(),
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc = result.data

    # RLS: verify the document's KB belongs to the requesting user
    kb_check = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_bases")
        .select("user_id")
        .eq("id", str(doc["knowledge_base_id"]))
        .single()
        .execute(),
    )
    if not kb_check.data or kb_check.data.get("user_id") != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    return DocumentStatusResponse(
        document_id=str(document_id),
        status=doc["status"],
        error_stage=doc.get("error_stage"),
        error_message=doc.get("error_message"),
        retry_count=doc.get("retry_count", 0),
    )
