"""
Document ingestion pipeline orchestrator.

Owns all status transitions on knowledge_base_documents.
Runs stages sequentially: extracting → chunking → embedding → completed.
Each stage is retried up to MAX_INGESTION_RETRIES times with INGESTION_RETRY_DELAYS backoff.
Token limit check (INGESTION_TOKEN_LIMIT) happens after extraction — rejects before embedding.

Supports stage-resumption for retry (KIN-336): run_ingestion_from_stage allows
restarting from chunking when extraction already succeeded. Extracted text is
persisted to Supabase Storage after extraction for this purpose.

KIN-467: Embedding uses platform Gemini key (no user BYOK required).
Token counting uses Gemini count_tokens API (low-frequency path).

Schema ref: db-schema-spec.md §12 (knowledge_base_documents)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID

from app.core.config import settings
from app.services.ingestion.chunker import chunk_document
from app.services.ingestion.embedder import EmbeddingService
from app.services.ingestion.extractor import extract_text
from app.services.ingestion.indexer import index_chunks
from app.services.ingestion.summarizer import generate_summary
from app.services.ingestion.tag_suggester import suggest_tags

logger = logging.getLogger(__name__)

# Per-stage timeout in seconds. Prevents indefinite hangs from blocking the
# pipeline. Generous to allow large documents (embedding many batches).
# Note: asyncio.wait_for on run_in_executor raises TimeoutError but cannot
# cancel the underlying thread — the thread may continue briefly. This is
# acceptable because we only need to unblock the pipeline and persist the error.
STAGE_TIMEOUT_SECONDS = 600  # 10 minutes


class TokenLimitExceeded(ValueError):
    """Raised when a document exceeds INGESTION_TOKEN_LIMIT tokens."""


async def _update_document(supabase, document_id: UUID, **fields) -> None:
    """Persist field updates to knowledge_base_documents. Raises on write failure."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents")
        .update(fields)
        .eq("id", str(document_id))
        .execute(),
    )
    # result.data may be [] on a successful update with no returning rows — that's fine.
    # Only raise if the call itself threw an exception (propagated by run_in_executor).
    _ = result  # noqa: F841


async def _store_extracted_text(supabase, document_id: UUID, text: str) -> None:
    """
    Persist extracted text to Supabase Storage for stage-resume retry (KIN-336).
    Non-fatal — if storage fails or times out, the document still processes.
    """
    try:
        loop = asyncio.get_running_loop()
        text_path = f"{document_id}/extracted.txt"
        await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
                .upload(text_path, text.encode("utf-8"), {"content-type": "text/plain"}),
            ),
            timeout=60,
        )
    except asyncio.TimeoutError:
        logger.warning("Extracted text storage timed out (non-fatal) for %s", document_id)
    except Exception as exc:
        logger.warning("Failed to persist extracted text (non-fatal): %s", exc)


async def _run_enrichment(
    supabase, document_id: UUID, text: str,
    anthropic_key: Optional[str] = None,
) -> None:
    """
    Run non-fatal enrichment steps: summary generation + tag suggestion.
    Uses user's BYOK Anthropic key. Failures logged and skipped — never fatal.
    """
    loop = asyncio.get_running_loop()

    # Summary
    try:
        summary = await loop.run_in_executor(
            None, lambda: generate_summary(text, anthropic_key=anthropic_key),
        )
        if summary:
            await _update_document(supabase, document_id, summary=summary)
    except Exception as exc:
        logger.warning("Summary generation failed (non-fatal) for %s: %s", document_id, exc)

    # Tag suggestions (KIN-336)
    try:
        tags = await loop.run_in_executor(
            None, lambda: suggest_tags(text, anthropic_key=anthropic_key),
        )
        if tags:
            await _update_document(supabase, document_id, tags=tags)
    except Exception as exc:
        logger.warning("Tag suggestion failed (non-fatal) for %s: %s", document_id, exc)


async def _fetch_document_title(
    supabase, document_id: UUID, fallback: str = "",
) -> str:
    """
    Fetch document title from DB for contextual chunk headers (KIN-468).
    Returns fallback (typically filename) if title is empty or lookup fails.
    Non-fatal — empty title means chunks get no header (backward-compatible).
    """
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: supabase.table("knowledge_base_documents")
            .select("title")
            .eq("id", str(document_id))
            .maybe_single()
            .execute(),
        )
        title = (result.data or {}).get("title", "") if result.data else ""
        return title or fallback
    except Exception as exc:
        logger.warning(
            "Failed to fetch document title for %s (non-fatal): %s", document_id, exc,
        )
        return fallback


async def _run_pipeline_stages(
    supabase,
    document_id: UUID,
    knowledge_base_id: UUID,
    project_id: Optional[UUID],
    agent_definition_id: Optional[UUID],
    text: str,
    total_tokens: int,
    document_title: str = "",
) -> None:
    """
    Run chunking → embedding → indexing → completed.
    Shared between full ingestion and stage-resume retry.

    Embedding uses platform Gemini key (no user BYOK required).
    """
    retry_count = 0

    async def _run_stage(stage_name: str, coro):
        """Update status to stage_name, run coro, retry on transient failure."""
        nonlocal retry_count

        for attempt in range(settings.MAX_INGESTION_RETRIES + 1):
            try:
                await _update_document(supabase, document_id, status=stage_name)
                return await asyncio.wait_for(
                    coro(), timeout=STAGE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                exc = TimeoutError(
                    f"Stage '{stage_name}' timed out after {STAGE_TIMEOUT_SECONDS}s"
                )
                logger.error(
                    "Stage %s timed out for document %s (attempt %d)",
                    stage_name, document_id, attempt + 1,
                )
                if attempt < settings.MAX_INGESTION_RETRIES:
                    retry_count += 1
                    delays = settings.INGESTION_RETRY_DELAYS
                    delay = delays[min(attempt, len(delays) - 1)]
                    await _update_document(supabase, document_id, retry_count=retry_count)
                    await asyncio.sleep(delay)
                else:
                    await _update_document(
                        supabase, document_id,
                        status="failed",
                        error_stage=stage_name,
                        error_message=str(exc)[:2000],
                        retry_count=retry_count,
                    )
                    raise exc
            except Exception as exc:
                if attempt < settings.MAX_INGESTION_RETRIES:
                    delays = settings.INGESTION_RETRY_DELAYS
                    delay = delays[min(attempt, len(delays) - 1)]
                    retry_count += 1
                    logger.warning(
                        "Stage %s failed (attempt %d/%d) for document %s: %s. "
                        "Retrying in %ds.",
                        stage_name,
                        attempt + 1,
                        settings.MAX_INGESTION_RETRIES,
                        document_id,
                        exc,
                        delay,
                    )
                    await _update_document(supabase, document_id, retry_count=retry_count)
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Stage %s exhausted retries for document %s: %s",
                        stage_name,
                        document_id,
                        exc,
                    )
                    await _update_document(
                        supabase,
                        document_id,
                        status="failed",
                        error_stage=stage_name,
                        error_message=str(exc)[:2000],
                        retry_count=retry_count,
                    )
                    raise

    # --- Stage: chunking ---
    async def _chunk():
        _loop = asyncio.get_running_loop()
        if settings.SEMANTIC_CHUNKING_ENABLED:
            from app.services.ingestion.semantic_chunker import chunk_document_semantic
            return await _loop.run_in_executor(
                None, lambda: chunk_document_semantic(text, total_tokens, document_title=document_title)
            )
        return await _loop.run_in_executor(
            None, lambda: chunk_document(text, total_tokens, document_title=document_title)
        )

    chunks = await _run_stage("chunking", _chunk)

    # --- Stage: embedding ---
    embedder = EmbeddingService()

    async def _embed():
        loop = asyncio.get_running_loop()
        texts = [c.text for c in chunks]
        return await loop.run_in_executor(None, lambda: embedder.embed_batch(texts))

    embeddings = await _run_stage("embedding", _embed)

    # Index chunks — failure sets error state so retry can recover
    try:
        await index_chunks(
            supabase,
            document_id,
            knowledge_base_id,
            project_id,
            agent_definition_id,
            chunks,
            embeddings,
        )
    except Exception as exc:
        logger.error("Indexing failed for document %s: %s", document_id, exc)
        await _update_document(
            supabase,
            document_id,
            status="failed",
            error_stage="embedding",  # closest stage — indexing is not a status enum value
            error_message=f"Indexing failed: {str(exc)[:1990]}",
            retry_count=retry_count,
        )
        raise

    await _update_document(
        supabase,
        document_id,
        status="completed",
        retry_count=retry_count,
    )
    logger.info(
        "Ingestion complete for document %s: %d chunks, retry_count=%d",
        document_id,
        len(chunks),
        retry_count,
    )


async def run_ingestion(
    supabase,
    document_id: UUID,
    knowledge_base_id: UUID,
    project_id: Optional[UUID],
    agent_definition_id: Optional[UUID],
    file_content: bytes,
    filename: str,
    content_type: str,
    anthropic_key: Optional[str] = None,
) -> None:
    """
    Run the full ingestion pipeline for one document.

    Stages:
      1. extracting  — text extraction via unstructured
      [optional]     — document-level summary + tag suggestions (ENRICHMENT_ENABLED)
      2. chunking    — word-based chunking (~375 words, ~75 word overlap)
      3. embedding   — Gemini Embedding 001 via platform key (KIN-467)
      4. indexing    — write chunks to knowledge_base_chunks (pgvector)
      5. completed   — final status update

    Each stage is retried up to settings.MAX_INGESTION_RETRIES times.
    Delays between retries: settings.INGESTION_RETRY_DELAYS (60s, 300s, 900s).
    Token limit exceeded → TokenLimitExceeded → status=failed, no retry.

    Args:
        supabase: Supabase service-role client.
        document_id: UUID of the knowledge_base_documents row (pre-created by upload endpoint).
        knowledge_base_id: Parent KB UUID.
        project_id: Scope — set if KB belongs to a Project.
        agent_definition_id: Scope — set if KB belongs to an AgentDefinition.
        file_content: Raw file bytes.
        filename: Original filename.
        content_type: MIME type.
        anthropic_key: User's decrypted Anthropic API key (optional, for enrichment).
    """
    retry_count = 0

    async def _run_stage(stage_name: str, coro):
        """Update status to stage_name, run coro, retry on transient failure."""
        nonlocal retry_count

        for attempt in range(settings.MAX_INGESTION_RETRIES + 1):
            try:
                await _update_document(supabase, document_id, status=stage_name)
                return await asyncio.wait_for(
                    coro(), timeout=STAGE_TIMEOUT_SECONDS,
                )
            except TokenLimitExceeded:
                raise
            except asyncio.TimeoutError:
                exc = TimeoutError(
                    f"Stage '{stage_name}' timed out after {STAGE_TIMEOUT_SECONDS}s"
                )
                logger.error(
                    "Stage %s timed out for document %s (attempt %d)",
                    stage_name, document_id, attempt + 1,
                )
                if attempt < settings.MAX_INGESTION_RETRIES:
                    retry_count += 1
                    delays = settings.INGESTION_RETRY_DELAYS
                    delay = delays[min(attempt, len(delays) - 1)]
                    await _update_document(supabase, document_id, retry_count=retry_count)
                    await asyncio.sleep(delay)
                else:
                    await _update_document(
                        supabase, document_id,
                        status="failed",
                        error_stage=stage_name,
                        error_message=str(exc)[:2000],
                        retry_count=retry_count,
                    )
                    raise exc
            except Exception as exc:
                if attempt < settings.MAX_INGESTION_RETRIES:
                    delays = settings.INGESTION_RETRY_DELAYS
                    delay = delays[min(attempt, len(delays) - 1)]
                    retry_count += 1
                    logger.warning(
                        "Stage %s failed (attempt %d/%d) for document %s: %s. "
                        "Retrying in %ds.",
                        stage_name,
                        attempt + 1,
                        settings.MAX_INGESTION_RETRIES,
                        document_id,
                        exc,
                        delay,
                    )
                    await _update_document(supabase, document_id, retry_count=retry_count)
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Stage %s exhausted retries for document %s: %s",
                        stage_name,
                        document_id,
                        exc,
                    )
                    await _update_document(
                        supabase,
                        document_id,
                        status="failed",
                        error_stage=stage_name,
                        error_message=str(exc)[:2000],
                        retry_count=retry_count,
                    )
                    raise

    try:
        # --- Stage: extracting ---
        async def _extract():
            _loop = asyncio.get_running_loop()
            text = await _loop.run_in_executor(
                None, lambda: extract_text(file_content, content_type, filename)
            )
            # Token count via Gemini API (low-frequency: once per document)
            embedder = EmbeddingService()
            total_tokens = await _loop.run_in_executor(
                None, lambda: embedder.count_tokens(text)
            )
            if total_tokens > settings.INGESTION_TOKEN_LIMIT:
                raise TokenLimitExceeded(
                    f"Document exceeds token limit: {total_tokens:,} > "
                    f"{settings.INGESTION_TOKEN_LIMIT:,}"
                )
            await _update_document(supabase, document_id, token_count=total_tokens)
            return text, total_tokens

        text, total_tokens = await _run_stage("extracting", _extract)

        # Persist extracted text to Storage for stage-resume retry (KIN-336)
        await _store_extracted_text(supabase, document_id, text)

        # Enrichment: summary + tags (non-fatal, outside retry loop)
        await _run_enrichment(supabase, document_id, text, anthropic_key=anthropic_key)

        # Use filename for contextual chunk headers (KIN-468).
        # documents.py sets title = original_filename, so the DB roundtrip is redundant
        # and was returning empty in prod (KIN-476 bugfix). Filename is always set.
        document_title = filename or "Untitled Document"
        _ = _fetch_document_title  # silence linter: function retained for retry path

        # Run remaining stages (chunking → embedding → indexing → completed)
        await _run_pipeline_stages(
            supabase, document_id, knowledge_base_id,
            project_id, agent_definition_id, text, total_tokens,
            document_title=document_title,
        )

    except TokenLimitExceeded as exc:
        await _update_document(
            supabase,
            document_id,
            status="failed",
            error_stage="extracting",
            error_message=str(exc)[:2000],
            retry_count=retry_count,
        )
        logger.warning("Document %s rejected: %s", document_id, exc)
    except Exception as exc:
        # Catch-all: persist error to DB so the UI shows a meaningful message.
        # _run_stage failures are already persisted, but exceptions from
        # _store_extracted_text, _run_enrichment, or _run_pipeline_stages
        # (outside _run_stage) would otherwise propagate silently through
        # FastAPI's background task runner with no DB update.
        logger.error(
            "Unhandled pipeline error for document %s: %s", document_id, exc,
        )
        try:
            await _update_document(
                supabase,
                document_id,
                status="failed",
                error_stage="unknown",
                error_message=f"Pipeline error: {str(exc)[:1980]}",
                retry_count=retry_count,
            )
        except Exception:
            logger.error(
                "Failed to persist error state for document %s", document_id,
            )
        raise


async def run_ingestion_from_stage(
    supabase,
    document_id: UUID,
    knowledge_base_id: UUID,
    project_id: Optional[UUID],
    agent_definition_id: Optional[UUID],
    start_stage: str,
    file_content: Optional[bytes] = None,
    extracted_text: Optional[str] = None,
    filename: str = "",
    content_type: str = "application/octet-stream",
    anthropic_key: Optional[str] = None,
) -> None:
    """
    Resume ingestion from a specific stage (KIN-336).

    Used by the retry endpoint after a failed ingestion.

    Args:
        start_stage: 'extracting' to re-run full pipeline, 'chunking' to skip extraction.
        file_content: Required if start_stage == 'extracting'.
        extracted_text: Required if start_stage == 'chunking'.
        anthropic_key: User's decrypted Anthropic API key (optional, for enrichment).
    """
    try:
        if start_stage == "extracting":
            if file_content is None:
                raise ValueError("file_content required for retry from extracting stage")
            await run_ingestion(
                supabase, document_id, knowledge_base_id,
                project_id, agent_definition_id,
                file_content, filename, content_type,
                anthropic_key=anthropic_key,
            )
        elif start_stage == "chunking":
            if extracted_text is None:
                raise ValueError("extracted_text required for retry from chunking stage")
            # Re-count tokens via Gemini API (low-frequency: once per retry)
            loop = asyncio.get_running_loop()
            embedder = EmbeddingService()
            total_tokens = await loop.run_in_executor(
                None, lambda: embedder.count_tokens(extracted_text)
            )
            await _update_document(supabase, document_id, token_count=total_tokens)
            # Re-run enrichment (tags/summary may have failed on first run too)
            await _run_enrichment(
                supabase, document_id, extracted_text, anthropic_key=anthropic_key,
            )
            # Fetch document title for contextual chunk headers (KIN-468)
            # Use filename directly — same rationale as main path (KIN-476 bugfix).
            document_title = filename or "Untitled Document"
            _ = _fetch_document_title  # retained for compatibility
            # Run chunking → embedding → indexing → completed
            await _run_pipeline_stages(
                supabase, document_id, knowledge_base_id,
                project_id, agent_definition_id, extracted_text, total_tokens,
                document_title=document_title,
            )
        else:
            raise ValueError(f"Invalid start_stage: {start_stage}")
    except Exception as exc:
        logger.error(
            "Unhandled error in stage-resume for document %s: %s",
            document_id, exc,
        )
        try:
            await _update_document(
                supabase,
                document_id,
                status="failed",
                error_stage=start_stage,
                error_message=f"Resume error: {str(exc)[:1980]}",
            )
        except Exception:
            logger.error(
                "Failed to persist error state for document %s", document_id,
            )
        raise
