"""
Optional document-level summary generation.

Enabled when settings.ENRICHMENT_ENABLED is True (default).
Uses user's BYOK Anthropic key + call_llm with CONVERSATION_COMPRESSION_MODEL (Haiku).

Failures are non-fatal — enrichment failure does NOT fail ingestion.
Returns None on any error; the pipeline stores null summary and continues.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.config import settings
from app.services.llm_client import call_llm

logger = logging.getLogger(__name__)

# First 8000 chars (~2000 tokens) of extracted text — enough for a meaningful summary
_SNIPPET_CHARS = 8_000

_SUMMARY_PROMPT = (
    "Summarize the following document in 2-3 sentences. "
    "Focus on the main topic, key points, and intended audience.\n\n"
    "Document:\n{text}"
)


def generate_summary(text: str, anthropic_key: Optional[str] = None) -> Optional[str]:
    """
    Generate a short document summary using the user's BYOK Anthropic key.

    Args:
        text: Full extracted document text.
        anthropic_key: User's decrypted Anthropic API key. None → skip.

    Returns:
        2-3 sentence summary string, or None if enrichment is disabled, key missing, or fails.
    """
    if not getattr(settings, "ENRICHMENT_ENABLED", True):
        return None

    if not anthropic_key:
        logger.info("No Anthropic key provided — skipping document summary")
        return None

    try:
        snippet = text[:_SNIPPET_CHARS]
        summary = call_llm(
            messages=[{"role": "user", "content": _SUMMARY_PROMPT.format(text=snippet)}],
            model=settings.CONVERSATION_COMPRESSION_MODEL,
            api_key=anthropic_key,
            max_tokens=200,
            timeout=20,
        )
        return summary.strip() if summary else None
    except Exception as exc:
        logger.warning("Document enrichment failed (non-fatal): %s", exc)
        return None
