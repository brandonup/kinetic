"""
Embedding service — wraps OpenAI text-embedding-3-large.

Uses the platform-owned OPENAI_API_KEY. Never uses BYOK keys.
Model: text-embedding-3-large (3072 dimensions)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMS = 3072


async def embed_text(text: str) -> list[float]:
    """Embed a single string. Returns a 3072-dim float vector.

    Raises RuntimeError if the platform OpenAI key is not configured or the
    API call fails — callers should catch and handle gracefully.
    """
    from app.config import get_settings

    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured (platform key required for embeddings)")

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _embed_sync(text, settings.OPENAI_API_KEY))


def _embed_sync(text: str, api_key: str) -> list[float]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        dimensions=EMBEDDING_DIMS,
    )
    return response.data[0].embedding


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple strings in a single API call (more efficient for bulk ops)."""
    from app.config import get_settings

    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: _embed_texts_sync(texts, settings.OPENAI_API_KEY)
    )


def _embed_texts_sync(texts: list[str], api_key: str) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        dimensions=EMBEDDING_DIMS,
    )
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
