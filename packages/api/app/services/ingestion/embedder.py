"""
Embedding service with batching, retries, and rate limit handling.

Ported from FounderPanel services/ingestion/embedding_service.py with Kinetic changes:
- Uses settings.PLATFORM_OPENAI_KEY (not OPENAI_API_KEY — that is a BYOK user key)
- Model sourced from settings.EMBEDDING_MODEL (default: text-embedding-3-large, 3072 dims)
- Batch size, retry params pulled from settings
"""

from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional, cast

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Create embeddings with batching and per-batch retries."""

    def __init__(
        self,
        model: Optional[str] = None,
        batch_size: Optional[int] = None,
        max_retries: Optional[int] = None,
        min_wait: Optional[int] = None,
        max_wait: Optional[int] = None,
        sleep_between_batches: Optional[float] = None,
    ) -> None:
        self.model = model or settings.EMBEDDING_MODEL
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self.max_retries = max_retries or settings.EMBEDDING_MAX_RETRIES
        self.min_wait = min_wait or settings.EMBEDDING_RETRY_MIN_WAIT
        self.max_wait = max_wait or settings.EMBEDDING_RETRY_MAX_WAIT
        self.sleep_between_batches = (
            sleep_between_batches
            if sleep_between_batches is not None
            else settings.EMBEDDING_SLEEP_BETWEEN_BATCHES
        )
        # Lazy-init: created on first embed call so __init__ never makes network calls
        self._client = None
        self._openai_module = None

    def embed_batch(
        self,
        texts: List[str],
        on_batch_complete: Optional[Callable[[int, List[List[float]]], None]] = None,
    ) -> List[List[float]]:
        """
        Embed texts in batches with retries and optional progress callback.

        Args:
            texts: List of text strings to embed.
            on_batch_complete: Optional callback(batch_idx, batch_embeddings) called
                after each batch succeeds.

        Returns:
            List of embedding vectors matching len(texts).

        Raises:
            RuntimeError: If PLATFORM_OPENAI_KEY is not configured.
            openai.RateLimitError et al.: Re-raised after max_retries exhausted.
        """
        if not texts:
            return []

        embeddings: List[List[float]] = []
        for batch_start in range(0, len(texts), self.batch_size):
            batch_idx = batch_start // self.batch_size
            batch = texts[batch_start : batch_start + self.batch_size]
            batch_embeddings = self._embed_single_batch(batch)
            embeddings.extend(batch_embeddings)

            if on_batch_complete:
                try:
                    on_batch_complete(batch_idx, batch_embeddings)
                except Exception as exc:
                    logger.warning("Embedding batch callback failed: %s", exc)

            if batch_start + self.batch_size < len(texts) and self.sleep_between_batches:
                time.sleep(self.sleep_between_batches)

        return cast(List[List[float]], embeddings)

    def _get_client(self):
        """Return (client, openai_module), creating the client once and reusing it."""
        if self._client is None:
            import openai  # type: ignore[import]

            if not settings.PLATFORM_OPENAI_KEY:
                raise RuntimeError(
                    "PLATFORM_OPENAI_KEY not configured — required for document embedding."
                )
            self._client = openai.OpenAI(api_key=settings.PLATFORM_OPENAI_KEY)
            self._openai_module = openai
        return self._client, self._openai_module

    def _embed_single_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a single batch with exponential backoff retry."""
        client, openai_module = self._get_client()

        retryable = (
            openai_module.RateLimitError,
            openai_module.APIConnectionError,
            openai_module.APITimeoutError,
            openai_module.InternalServerError,
        )

        # Build the decorated invoker once per EmbeddingService instance.
        # Keyed on retryable tuple identity — safe since openai_module is fixed after first call.
        if not hasattr(self, "_invoke"):
            @retry(
                reraise=True,
                stop=stop_after_attempt(self.max_retries + 1),
                wait=wait_exponential(min=self.min_wait, max=self.max_wait),
                retry=retry_if_exception_type(retryable),
            )
            def _invoke(batch: List[str]) -> List[List[float]]:
                response = client.embeddings.create(input=batch, model=self.model)
                return [cast(List[float], item.embedding) for item in response.data]

            self._invoke = _invoke

        return cast(List[List[float]], self._invoke(texts))
