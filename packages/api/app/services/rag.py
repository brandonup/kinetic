"""
RAG retrieval service — Kinetic API.

MVP: zero-LLM retrieval path.
Pipeline: embed query → vector search → MMR → similarity threshold → token budget → inject.

ADR ref: docs/adr-002-rag-retrieval-pipeline.md
Implementation ticket: KIN-258 (Big Head — Sprint 3, separate track)

This module is imported by context_stack.py for Layer 8 (Project KB RAG)
and Layer 9 (Agent KB RAG, stub).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    document_title: str


async def retrieve(
    knowledge_base_id: str,
    query: str,
    supabase: Any,
    *,
    top_k: int = 8,
    similarity_threshold: float = 0.3,
    max_tokens: int = 2048,
) -> list[RetrievedChunk]:
    """
    Retrieve relevant chunks from a knowledge base for a given query.

    Sprint 3: stub — returns empty list.
    KIN-258 implements the full pipeline (embedding + pgvector + MMR).
    Full implementation replaces this stub without any changes to callers.
    """
    # TODO KIN-258: implement full RAG pipeline
    # 1. Embed query with platform OpenAI key (text-embedding-3-large)
    # 2. pgvector cosine similarity search (top_k candidates)
    # 3. MMR selection (MMR_TOP_K=8, lambda=0.6)
    # 4. Filter by similarity_threshold (0.3)
    # 5. Token budget enforcement (greedy fill by score)
    # 6. Return RetrievedChunk list
    return []


def format_chunks_for_prompt(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks as a prompt-ready string."""
    if not chunks:
        return ""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[{i}] {chunk.document_title}\n{chunk.text}")
    return "\n\n".join(parts)
