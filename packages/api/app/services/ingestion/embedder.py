"""
Embedding service using Gemini Embedding 001 with batching, retries, and rate limit handling.

Platform-owned key (GEMINI_API_KEY) — no user BYOK required for embedding.
Model: gemini-embedding-001 (3072 dims native; SDK normalizes at native dim).
Tickets: KIN-467, KIN-476.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional, cast

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Create embeddings via Gemini with batching and per-batch retries."""

    DEFAULT_REQUEST_TIMEOUT: int = 120

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
        # Lazy-init: created on first call so __init__ never makes network calls
        self._client = None

    def embed_batch(
        self,
        texts: List[str],
        on_batch_complete: Optional[Callable[[int, List[List[float]]], None]] = None,
    ) -> List[List[float]]:
        """
        Embed texts in batches with retries and optional progress callback.

        Returns:
            List of embedding vectors (settings.EMBEDDING_DIMS each — 3072 by default) matching len(texts).

        Raises:
            RuntimeError: If GEMINI_API_KEY is not configured.
            google.genai errors: Re-raised after max_retries exhausted.
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

    def count_tokens(self, text: str) -> int:
        """Count tokens via Gemini API. Use for low-frequency paths only (pipeline/retrieval)."""
        client = self._get_client()
        result = client.models.count_tokens(model=self.model, contents=text)
        return result.total_tokens

    def _get_client(self):
        """Return genai.Client, creating once and reusing."""
        if self._client is None:
            from google import genai  # type: ignore[import]

            if not settings.GEMINI_API_KEY:
                raise RuntimeError(
                    "GEMINI_API_KEY not configured. "
                    "Set the environment variable to enable embeddings."
                )
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    def _embed_single_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a single batch with exponential backoff retry."""
        from google.genai import types  # local import keeps __init__ side-effect-free

        client = self._get_client()

        # gemini-embedding-001 native dim is 3072 with automatic L2 normalization.
        # When `output_dimensionality` is set to a non-native value, the SDK returns
        # a truncated, unnormalized vector — the caller must normalize itself.
        # We only request a non-native dim explicitly to keep the normalized path.
        embed_config = None
        if settings.EMBEDDING_DIMS != 3072:
            embed_config = types.EmbedContentConfig(
                output_dimensionality=settings.EMBEDDING_DIMS
            )

        # Build the decorated invoker once per EmbeddingService instance.
        if not hasattr(self, "_invoke"):
            @retry(
                reraise=True,
                stop=stop_after_attempt(self.max_retries + 1),
                wait=wait_exponential(min=self.min_wait, max=self.max_wait),
                retry=retry_if_exception_type((ConnectionError, TimeoutError, Exception)),
            )
            def _invoke(batch: List[str]) -> List[List[float]]:
                kwargs = {"model": self.model, "contents": batch}
                if embed_config is not None:
                    kwargs["config"] = embed_config
                result = client.models.embed_content(**kwargs)
                return [list(e.values) for e in result.embeddings]

            self._invoke = _invoke

        return cast(List[List[float]], self._invoke(texts))
