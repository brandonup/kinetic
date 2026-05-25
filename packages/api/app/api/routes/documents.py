"""
Document upload, status, and retry endpoints.

POST /api/v1/documents/upload
  - Validates file size (25 MB limit) at the API boundary
  - Creates knowledge_base_documents row with status='pending'
  - Stores file in Supabase Storage (for retry support — KIN-336)
  - Dispatches ingestion pipeline via TaskDispatcher (background)
  - Returns {document_id, status} immediately

GET /api/v1/documents/{document_id}
  - Returns current document status, tags, and error info (for polling / retry UX)

POST /api/v1/documents/{document_id}/retry
  - Re-triggers ingestion from the failed stage (KIN-336)
  - Downloads file/text from Supabase Storage, resets status, dispatches pipeline

Schema ref: db-schema-spec.md §12 (knowledge_base_documents)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth.deps import CurrentUser, get_current_user
from app.core.config import settings
from app.db.supabase_client import create_supabase, get_supabase
from app.services.background import TaskDispatcher
from app.services.ingestion.document_date import (
    MIN_PLAUSIBLE_DATE,
    is_plausible_document_date,
)
from app.services.ingestion.pipeline import run_ingestion, run_ingestion_from_stage
from app.services.user_keys import fetch_user_key_async

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
    tags: list[str] = []
    is_retryable: bool = True


class DeleteDocumentResponse(BaseModel):
    document_id: str
    deleted: bool


class RetryResponse(BaseModel):
    document_id: str
    status: str
    message: str


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    knowledge_base_id: UUID = Form(...),
    document_date: date | None = Form(None),
    current_user: CurrentUser = Depends(get_current_user),
) -> UploadResponse:
    """
    Upload a document to a Knowledge Base and start background ingestion.

    Validates file size at the boundary (413 if > 25 MB).
    Creates a knowledge_base_documents row immediately and returns.
    Ingestion runs in the background: pending → extracting → chunking → embedding → completed.

    Optional ``document_date`` is the publication date used for recency-aware
    retrieval (KIN-481). FastAPI rejects malformed ISO strings with 422; a
    parseable but implausible value (pre-2015 or beyond today+1d) is also
    rejected with 422 so the caller learns of the bad input.
    """
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds 25 MB upload limit ({len(content):,} bytes received).",
        )

    if document_date is not None and not is_plausible_document_date(document_date):
        raise HTTPException(
            status_code=422,
            detail=(
                f"document_date {document_date.isoformat()} is outside the supported "
                f"range [{MIN_PLAUSIBLE_DATE.isoformat()}, today+1d]."
            ),
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
    # RLS: only the KB owner can upload to it. Per policies/authorization.md rule 2,
    # cross-tenant access returns 404 (not 403) to avoid leaking resource existence.
    if kb.get("user_id") != current_user.user_id:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")

    project_id = UUID(kb["project_id"]) if kb.get("project_id") else None
    agent_definition_id = UUID(kb["agent_definition_id"]) if kb.get("agent_definition_id") else None

    document_id = uuid4()
    content_type = file.content_type or "application/octet-stream"
    original_filename = file.filename or "Untitled"

    # Create document row with status=pending
    insert_row: dict = {
        "id": str(document_id),
        "knowledge_base_id": str(knowledge_base_id),
        "title": original_filename,
        "file_type": content_type,
        "file_size_bytes": len(content),
        "status": "pending",
        "retry_count": 0,
    }
    if document_date is not None:
        insert_row["document_date"] = document_date.isoformat()
    insert_result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents").insert(insert_row).execute(),
    )
    if not insert_result.data:
        raise RuntimeError(f"Failed to create document row for {document_id}")

    # Store file in Supabase Storage for retry support (KIN-336)
    # Split into two guarded blocks: only set storage_uri if upload succeeds.
    storage_path = f"{document_id}/{original_filename}"
    storage_ok = False
    try:
        await loop.run_in_executor(
            None,
            lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
            .upload(storage_path, content, {"content-type": content_type}),
        )
        storage_ok = True
    except Exception as exc:
        logger.warning("Failed to upload file to Storage (non-fatal): %s", exc)

    if storage_ok:
        try:
            await loop.run_in_executor(
                None,
                lambda: supabase.table("knowledge_base_documents")
                .update({"storage_uri": storage_path})
                .eq("id", str(document_id))
                .execute(),
            )
        except Exception as exc:
            logger.warning("Failed to set storage_uri (non-fatal): %s", exc)

    # Dispatch pipeline. Embedding uses platform Gemini key — no user BYOK needed (KIN-467).
    # Guard: if an unexpected (non-HTTP) exception occurs after the document row was inserted,
    # clean up the orphaned pending row so it doesn't linger in the UI.
    try:
        anthropic_key = await fetch_user_key_async(supabase, current_user.user_id, "anthropic")

        # Create a dedicated Supabase client for the background pipeline.
        # The singleton (get_supabase) shares one httpx HTTP/2 connection pool —
        # concurrent executor threads (pipeline + status polls) cause EAGAIN.
        pipeline_supabase = create_supabase()
        dispatcher = TaskDispatcher(background_tasks)
        dispatcher.dispatch(
            run_ingestion,
            pipeline_supabase,
            document_id,
            knowledge_base_id,
            project_id,
            agent_definition_id,
            content,
            original_filename,
            content_type,
            anthropic_key,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Upload failed after document row created — deleting orphaned row %s: %s",
            document_id,
            exc,
        )
        try:
            await loop.run_in_executor(
                None,
                lambda: supabase.table("knowledge_base_documents")
                .delete()
                .eq("id", str(document_id))
                .execute(),
            )
        except Exception as cleanup_exc:
            logger.error("Failed to clean up orphaned document row %s: %s", document_id, cleanup_exc)
        raise

    return UploadResponse(document_id=str(document_id), status="pending")


@router.get("/{document_id}", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentStatusResponse:
    """Return current ingestion status for a document, including tags."""
    supabase = get_supabase()
    loop = asyncio.get_running_loop()

    result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents")
        .select("id, status, error_stage, error_message, retry_count, knowledge_base_id, tags")
        .eq("id", str(document_id))
        .is_("deleted_at", "null")
        .limit(1)
        .execute(),
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc = result.data[0]

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
        raise HTTPException(status_code=404, detail="Document not found.")

    error_message = doc.get("error_message")
    # Coupled to pipeline error wording: TokenLimitExceeded raises "Document exceeds token limit: ..."
    is_retryable = "token limit" not in (error_message or "").lower()

    return DocumentStatusResponse(
        document_id=str(document_id),
        status=doc["status"],
        error_stage=doc.get("error_stage"),
        error_message=error_message,
        retry_count=doc.get("retry_count", 0),
        tags=doc.get("tags") or [],
        is_retryable=is_retryable,
    )


@router.post("/{document_id}/retry", response_model=RetryResponse)
async def retry_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
) -> RetryResponse:
    """
    Re-trigger ingestion for a failed document from the failed stage (KIN-336).

    - Only documents with status='failed' can be retried.
    - Downloads file/text from Supabase Storage based on error_stage.
    - Cleans up any partial chunks from previous attempt.
    - Resets retry_count, error_stage, error_message, dispatches pipeline.
    """
    supabase = get_supabase()
    loop = asyncio.get_running_loop()

    # Fetch document
    result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents")
        .select(
            "id, status, error_stage, storage_uri, knowledge_base_id, "
            "file_type, title"
        )
        .eq("id", str(document_id))
        .is_("deleted_at", "null")
        .single()
        .execute(),
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc = result.data

    # RLS: verify ownership via KB chain FIRST (prevents state leakage cross-tenant)
    kb_check = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_bases")
        .select("user_id, project_id, agent_definition_id")
        .eq("id", str(doc["knowledge_base_id"]))
        .single()
        .execute(),
    )
    if not kb_check.data or kb_check.data.get("user_id") != current_user.user_id:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Only failed documents can be retried
    if doc["status"] != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Document status is '{doc['status']}', not 'failed'. Only failed documents can be retried.",
        )

    kb = kb_check.data
    knowledge_base_id = UUID(doc["knowledge_base_id"])
    project_id = UUID(kb["project_id"]) if kb.get("project_id") else None
    agent_definition_id = UUID(kb["agent_definition_id"]) if kb.get("agent_definition_id") else None
    error_stage = doc.get("error_stage", "extracting")
    storage_uri = doc.get("storage_uri")

    # Determine start stage and download required data
    if error_stage == "extracting":
        start_stage = "extracting"
        if not storage_uri:
            raise HTTPException(
                status_code=500,
                detail="File not available for retry. Please re-upload the document.",
            )
        try:
            file_content = await loop.run_in_executor(
                None,
                lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
                .download(storage_uri),
            )
        except Exception as exc:
            logger.error("Failed to download file for retry: %s", exc)
            raise HTTPException(
                status_code=500,
                detail="File not available for retry. Please re-upload the document.",
            )
        extracted_text = None
    else:
        # chunking or embedding — try to download extracted text
        start_stage = "chunking"
        text_path = f"{document_id}/extracted.txt"
        try:
            text_bytes = await loop.run_in_executor(
                None,
                lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
                .download(text_path),
            )
            extracted_text = text_bytes.decode("utf-8")
        except Exception as exc:
            # Fall back to full re-extraction if text not available
            logger.warning("Extracted text not available, falling back to full re-extraction: %s", exc)
            if not storage_uri:
                raise HTTPException(
                    status_code=500,
                    detail="Neither extracted text nor file available for retry. Please re-upload.",
                )
            try:
                file_content = await loop.run_in_executor(
                    None,
                    lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
                    .download(storage_uri),
                )
            except Exception:
                raise HTTPException(
                    status_code=500,
                    detail="File not available for retry. Please re-upload the document.",
                )
            start_stage = "extracting"
            extracted_text = None
        else:
            file_content = None

    # Atomic status reset FIRST — uses status='failed' in WHERE clause to prevent
    # race condition where two concurrent retries both claim the same document.
    # If no rows updated, another retry already started. Must run before chunk
    # cleanup to avoid deleting chunks while another retry is mid-pipeline.
    try:
        reset_result = await loop.run_in_executor(
            None,
            lambda: supabase.table("knowledge_base_documents")
            .update({
                "status": "pending",
                "error_stage": None,
                "error_message": None,
                "retry_count": 0,
            })
            .eq("id", str(document_id))
            .eq("status", "failed")
            .execute(),
        )
        if not reset_result.data:
            raise HTTPException(
                status_code=409,
                detail="Document retry already in progress.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to reset document %s status for retry: %s", document_id, exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to reset document status. Please try again.",
        )

    # Clean up any partial chunks from previous attempt (idempotency)
    # Safe to run after atomic lock — only the winning retry gets here.
    try:
        await loop.run_in_executor(
            None,
            lambda: supabase.table("knowledge_base_chunks")
            .delete()
            .eq("document_id", str(document_id))
            .execute(),
        )
    except Exception as exc:
        logger.warning("Chunk cleanup failed (non-fatal): %s", exc)

    # Fetch BYOK Anthropic key for enrichment (embedding uses platform Gemini key)
    anthropic_key = await fetch_user_key_async(supabase, current_user.user_id, "anthropic")

    # Dispatch retry pipeline — fresh client to avoid HTTP/2 contention
    pipeline_supabase = create_supabase()
    dispatcher = TaskDispatcher(background_tasks)
    dispatcher.dispatch(
        run_ingestion_from_stage,
        pipeline_supabase,
        document_id,
        knowledge_base_id,
        project_id,
        agent_definition_id,
        start_stage,
        file_content,
        extracted_text,
        doc.get("title", ""),
        doc.get("file_type", "application/octet-stream"),
        anthropic_key,
    )

    return RetryResponse(
        document_id=str(document_id),
        status="pending",
        message=f"Retry initiated from {start_stage} stage.",
    )


@router.delete("/{document_id}", response_model=DeleteDocumentResponse)
async def delete_document(
    document_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> DeleteDocumentResponse:
    """
    Hard-delete a single document.

    Chunks are removed automatically via ON DELETE CASCADE.
    Storage files are cleaned eagerly (non-fatal).
    Rejects deletion of actively-ingesting documents (409).
    """
    from app.core.constants import ACTIVE_INGESTION_STATUSES

    supabase = get_supabase()
    loop = asyncio.get_running_loop()

    # Fetch document
    result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents")
        .select("id, status, knowledge_base_id, title, storage_uri")
        .eq("id", str(document_id))
        .limit(1)
        .execute(),
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc = result.data[0]

    # Auth: verify ownership via KB chain (404 for anti-enumeration)
    kb_check = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_bases")
        .select("user_id")
        .eq("id", str(doc["knowledge_base_id"]))
        .single()
        .execute(),
    )
    if not kb_check.data or kb_check.data.get("user_id") != current_user.user_id:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Guard: reject active ingestion
    if doc["status"] in ACTIVE_INGESTION_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete document while status is '{doc['status']}'. Wait for ingestion to complete or fail.",
        )

    # Hard-delete — chunks removed automatically via ON DELETE CASCADE
    delete_result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents")
        .delete()
        .eq("id", str(document_id))
        .execute(),
    )
    if not delete_result.data:
        logger.error("Failed to delete document %s", document_id)
        raise HTTPException(status_code=500, detail="Failed to delete document.")

    # Eager storage cleanup (non-fatal) — will be handled by cleanup job once it exists
    storage_uri = doc.get("storage_uri")
    doc_id_str = str(document_id)
    for path in [storage_uri, f"{doc_id_str}/extracted.txt"]:
        if path:
            try:
                await loop.run_in_executor(
                    None,
                    lambda p=path: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([p]),
                )
            except Exception as exc:
                logger.warning("Storage cleanup failed for %s (non-fatal): %s", path, exc)

    return DeleteDocumentResponse(document_id=doc_id_str, deleted=True)
