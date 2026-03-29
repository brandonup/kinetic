"""
AI-generated tag suggestions for uploaded documents.

Enabled when settings.ENRICHMENT_ENABLED is True (default).
Uses user's BYOK Anthropic key + call_llm with CONVERSATION_COMPRESSION_MODEL (Haiku).

Failures are non-fatal — tag suggestion failure does NOT fail ingestion.
Returns empty list on any error; the pipeline stores empty tags and continues.

Spec ref: docs/prd.md §7 — "AI auto-suggests tags and metadata on upload"
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.core.config import settings
from app.services.llm_client import call_llm

logger = logging.getLogger(__name__)

# First 8000 chars (~2000 tokens) — enough context for meaningful tags
_SNIPPET_CHARS = 8_000

_TAG_PROMPT = (
    "Generate 3 to 5 short tags (1-3 words each) that describe the main topics "
    "of the following document. Return ONLY a comma-separated list of tags, "
    "nothing else. Example: strategy, leadership, decision-making\n\n"
    "Document:\n{text}"
)


def suggest_tags(text: str, anthropic_key: Optional[str] = None) -> List[str]:
    """
    Generate tag suggestions for a document using the user's BYOK Anthropic key.

    Args:
        text: Full extracted document text.
        anthropic_key: User's decrypted Anthropic API key. None → skip.

    Returns:
        List of 3-5 lowercase tag strings, or empty list if disabled, key missing, or fails.
    """
    if not getattr(settings, "ENRICHMENT_ENABLED", True):
        return []

    if not anthropic_key:
        logger.info("No Anthropic key provided — skipping tag suggestion")
        return []

    try:
        snippet = text[:_SNIPPET_CHARS]
        response = call_llm(
            messages=[{"role": "user", "content": _TAG_PROMPT.format(text=snippet)}],
            model=settings.CONVERSATION_COMPRESSION_MODEL,
            api_key=anthropic_key,
            max_tokens=100,
            timeout=15,
        )
        if not response:
            return []

        # Parse comma-separated tags, strip whitespace, lowercase, remove empties
        tags = [tag.strip().lower() for tag in response.split(",") if tag.strip()]
        # Cap at 5 tags max
        return tags[:5]
    except Exception as exc:
        logger.warning("Tag suggestion failed (non-fatal): %s", exc)
        return []
