"""
Document ingestion pipeline orchestrator.

Owns all status transitions on knowledge_base_documents.
Runs stages sequentially: extracting → chunking → embedding → completed.
Each stage is retried up to MAX_INGESTION_RETRIES times with INGESTION_RETRY_DELAYS backoff.
Token limit check (INGESTION_TOKEN_LIMIT) happens after extraction — rejects before embedding.

Schema ref: db-schema-spec.md §12 (knowledge_base_documents)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID

import tiktoken

from app.core.config import settings
from app.services.ingestion.chunker import chunk_document
from app.services.ingestion.embedder import EmbeddingService
from app.services.ingestion.extractor import extract_text
from app.services.ingestion.indexer import index_chunks
from app.services.ingestion.summarizer import generate_summary

logger = logging.getLogger(__name__)


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


async def run_ingestion(
    supabase,
    document_id: UUID,
    knowledge_base_id: UUID,
    project_id: Optional[UUID],
    agent_definition_id: Optional[UUID],
    file_content: bytes,
    filename: str,
    content_type: str,
) -> None:
    """
    Run the full ingestion pipeline for one document.

    Stages:
      1. extracting  — text extraction via unstructured
      2. chunking    — fixed-size token chunking (~500 tokens, ~50 overlap)
      3. embedding   — text-embedding-3-large via platform OpenAI key
      [optional]     — document-level summary (ENRICHMENT_ENABLED)
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
    """
    retry_count = 0

    async def _run_stage(stage_name: str, coro):
        """Update status to stage_name, run coro, retry on transient failure."""
        nonlocal retry_count

        for attempt in range(settings.MAX_INGESTION_RETRIES + 1):
            try:
                await _update_document(supabase, document_id, status=stage_name)
                return await coro()
            except TokenLimitExceeded:
                # Hard rejection — do not retry
                raise
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
            enc = tiktoken.get_encoding("cl100k_base")
            total_tokens = len(enc.encode(text))
            if total_tokens > settings.INGESTION_TOKEN_LIMIT:
                raise TokenLimitExceeded(
                    f"Document exceeds token limit: {total_tokens:,} > "
                    f"{settings.INGESTION_TOKEN_LIMIT:,}"
                )
            await _update_document(supabase, document_id, token_count=total_tokens)
            return text, total_tokens

        text, total_tokens = await _run_stage("extracting", _extract)

        # Optional enrichment — outside retry loop, non-fatal.
        # generate_summary makes a blocking LiteLLM HTTP call — run in executor.
        loop = asyncio.get_running_loop()
        summary = await loop.run_in_executor(None, lambda: generate_summary(text))
        if summary:
            await _update_document(supabase, document_id, summary=summary)

        # --- Stage: chunking ---
        async def _chunk():
            _loop = asyncio.get_running_loop()
            return await _loop.run_in_executor(
                None, lambda: chunk_document(text, total_tokens)
            )

        chunks = await _run_stage("chunking", _chunk)

        # --- Stage: embedding ---
        embedder = EmbeddingService()

        async def _embed():
            loop = asyncio.get_running_loop()
            texts = [c.text for c in chunks]
            return await loop.run_in_executor(None, lambda: embedder.embed_batch(texts))

        embeddings = await _run_stage("embedding", _embed)

        # Index chunks (outside retry — indexer raises on failure, caller can retry from outside)
        await index_chunks(
            supabase,
            document_id,
            knowledge_base_id,
            project_id,
            agent_definition_id,
            chunks,
            embeddings,
        )

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
    except Exception:
        # Stage failure already persisted by _run_stage — just propagate
        raise
