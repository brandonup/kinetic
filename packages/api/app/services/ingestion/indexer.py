"""
pgvector chunk indexer.

Writes knowledge_base_chunks rows to Supabase.
All columns per db-schema-spec.md §13.

Scope columns (project_id, agent_definition_id) are resolved from the parent
knowledge_base by the caller — the indexer is scope-agnostic.

All Supabase calls are wrapped in run_in_executor (sync client in async context).
Write failures raise RuntimeError — never silently swallowed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional
from uuid import UUID

from app.core.config import settings
from app.services.ingestion.chunker import Chunk

logger = logging.getLogger(__name__)

# Transient errors that warrant a retry (network hiccups, connection resets).
_TRANSIENT_ERRORS = ("Resource temporarily unavailable", "ReadError", "ConnectError")
_MAX_INDEX_RETRIES = 2
_INDEX_RETRY_DELAYS = (2, 5)  # seconds


async def index_chunks(
    supabase,
    document_id: UUID,
    knowledge_base_id: UUID,
    project_id: Optional[UUID],
    agent_definition_id: Optional[UUID],
    chunks: List[Chunk],
    embeddings: List[List[float]],
) -> int:
    """
    Insert chunk rows into knowledge_base_chunks.

    Args:
        supabase: Supabase client (sync — wrapped in run_in_executor).
        document_id: Parent document UUID.
        knowledge_base_id: Parent KB UUID (denormalized).
        project_id: Scope column — set if KB belongs to a Project.
        agent_definition_id: Scope column — set if KB belongs to an AgentDefinition.
        chunks: Chunk objects from the chunker.
        embeddings: Embedding vectors matching len(chunks).

    Returns:
        Number of chunks inserted.

    Raises:
        ValueError: chunks/embeddings length mismatch.
        RuntimeError: Supabase insert returned no data.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"Chunk/embedding count mismatch: {len(chunks)} chunks vs {len(embeddings)} embeddings"
        )

    if not chunks:
        logger.warning("No chunks to index for document %s", document_id)
        return 0

    rows = [
        {
            "document_id": str(document_id),
            "knowledge_base_id": str(knowledge_base_id),
            "project_id": str(project_id) if project_id else None,
            "agent_definition_id": str(agent_definition_id) if agent_definition_id else None,
            "text": chunk.text,
            "embedding": embedding,
            "section_path": chunk.section_path,
            "page_range": chunk.page_range,
            "chunk_index": chunk.chunk_index,
            "embedding_model": "gemini-embedding-001",  # hardcoded — backstop for stale env var (KIN-476 bugfix)
        }
        for chunk, embedding in zip(chunks, embeddings)
    ]

    loop = asyncio.get_running_loop()

    last_exc: Exception | None = None
    for attempt in range(_MAX_INDEX_RETRIES + 1):
        try:
            result = await loop.run_in_executor(
                None,
                lambda: supabase.table("knowledge_base_chunks").insert(rows).execute(),
            )
            break
        except Exception as exc:
            last_exc = exc
            err_str = str(exc)
            is_transient = any(t in err_str for t in _TRANSIENT_ERRORS)
            if is_transient and attempt < _MAX_INDEX_RETRIES:
                delay = _INDEX_RETRY_DELAYS[min(attempt, len(_INDEX_RETRY_DELAYS) - 1)]
                logger.warning(
                    "Transient error indexing document %s (attempt %d/%d): %s. "
                    "Retrying in %ds.",
                    document_id, attempt + 1, _MAX_INDEX_RETRIES, exc, delay,
                )
                await asyncio.sleep(delay)
            else:
                raise
    else:
        raise last_exc  # type: ignore[misc]

    if not result.data:
        raise RuntimeError(
            f"knowledge_base_chunks insert returned no data for document {document_id}"
        )

    count = len(result.data)
    logger.info("Indexed %d chunks for document %s", count, document_id)
    return count
