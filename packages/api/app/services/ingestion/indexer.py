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
            "embedding_model": settings.EMBEDDING_MODEL,
        }
        for chunk, embedding in zip(chunks, embeddings)
    ]

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_chunks").insert(rows).execute(),
    )

    if not result.data:
        raise RuntimeError(
            f"knowledge_base_chunks insert returned no data for document {document_id}"
        )

    count = len(result.data)
    logger.info("Indexed %d chunks for document %s", count, document_id)
    return count
