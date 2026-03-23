"""
Conversation history compression service — KIN-277.

Implements rolling summary compression for conversation history.
Triggered from the generation endpoint when message count crosses
COMPRESSION_THRESHOLD.

Architecture:
  1. Fetch messages not yet covered by the most recent summary.
  2. Call LLM (user's BYOK key) to generate a rolling summary.
  3. Persist the new summary row in conversation_summaries.
  4. Future context assembly reads the summary + VERBATIM_WINDOW recent messages.

Threshold defaults (ADR-004 to confirm):
  COMPRESSION_THRESHOLD = 20 messages
  VERBATIM_WINDOW       = 6 messages (kept verbatim after summary)

Fallback (MEMORY.md 2026-03-21):
  If BYOK key call fails, truncate oldest messages without summarisation.
  Notify user inline via an SSE 'warning' event (generation endpoint handles this).

Spec ref: docs/specs/kin-257-projects-conversations-spec.md §2.7
ADR ref: ADR-004 (Gilfoyle — threshold values, verbatim window, model choice)
Schema ref: docs/db-schema-spec.md §7 (conversation_summaries)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

try:
    import litellm  # type: ignore  # noqa: F401
except ImportError:  # pragma: no cover
    litellm = None  # type: ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (ADR-004 to lock final values)
# ---------------------------------------------------------------------------

COMPRESSION_THRESHOLD = 20   # Compress when message count exceeds this
VERBATIM_WINDOW = 6          # Keep this many recent messages verbatim post-summary

_SUMMARY_PROMPT_TEMPLATE = """\
You are summarising a conversation to preserve its key context for future messages.

Produce a concise but information-dense summary of the conversation below. Focus on:
- Key decisions made
- Important facts, numbers, or constraints mentioned
- Open questions or next steps
- Context needed to understand future messages

Keep the summary under 400 words. Do not add commentary — just the summary.

CONVERSATION:
{conversation_text}
"""


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _fetch_messages(supabase: Any, conversation_id: str) -> list[dict]:
    result = await _run(
        lambda: supabase.table("messages")
        .select("id, role, content, sequence")
        .eq("conversation_id", conversation_id)
        .neq("role", "system")
        .order("sequence", desc=False)
        .execute()
    )
    return result.data or []


async def _fetch_latest_summary(
    supabase: Any, conversation_id: str
) -> Optional[dict]:
    result = await _run(
        lambda: supabase.table("conversation_summaries")
        .select("summary_text, messages_covered_up_to")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


async def _persist_summary(
    supabase: Any,
    conversation_id: str,
    summary_text: str,
    messages_covered_up_to: int,
    model: Optional[str],
) -> None:
    await _run(
        lambda: supabase.table("conversation_summaries")
        .insert({
            "conversation_id": conversation_id,
            "summary_text": summary_text,
            "messages_covered_up_to": messages_covered_up_to,
            "model": model,
        })
        .execute()
    )


def _format_messages_for_summary(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        role = m["role"].upper()
        lines.append(f"{role}: {m['content']}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# LLM call (BYOK)
# ---------------------------------------------------------------------------


async def _call_llm_for_summary(
    conversation_text: str,
    api_key: str,
    model_string: str,
) -> Optional[str]:
    """Call LiteLLM to generate a summary. Returns None on failure."""
    try:
        prompt = _SUMMARY_PROMPT_TEMPLATE.format(conversation_text=conversation_text)
        response = await litellm.acompletion(
            model=model_string,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.3,
            api_key=api_key,
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.warning("Compression LLM call failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def compress(
    conversation_id: str,
    supabase: Any,
    *,
    api_key: Optional[str] = None,
    model_string: Optional[str] = None,
) -> bool:
    """
    Run rolling summary compression for a conversation.

    Called as a background task from the generation endpoint when
    message_count > COMPRESSION_THRESHOLD.

    Parameters
    ----------
    conversation_id : str
        UUID of the conversation to compress.
    supabase : Any
        Supabase client.
    api_key : str | None
        User's BYOK key for the LLM call. If None, falls back to truncation.
    model_string : str | None
        LiteLLM model string, e.g. ``"anthropic/claude-haiku-4-5-20251001"``.

    Returns
    -------
    bool
        True if a summary was written. False if compression was skipped or failed.
    """
    messages = await _fetch_messages(supabase, conversation_id)
    if len(messages) <= COMPRESSION_THRESHOLD:
        return False  # Nothing to compress yet

    latest_summary = await _fetch_latest_summary(supabase, conversation_id)

    # Determine which messages need to be summarised
    already_covered = latest_summary["messages_covered_up_to"] if latest_summary else -1
    to_summarise = [m for m in messages if m["sequence"] > already_covered]

    # Keep VERBATIM_WINDOW messages out of the summary (they'll be injected verbatim)
    messages_to_summarise = to_summarise[:-VERBATIM_WINDOW] if len(to_summarise) > VERBATIM_WINDOW else []
    if not messages_to_summarise:
        return False  # Not enough new messages to warrant a new summary

    # Build text for LLM
    prior_summary_text = latest_summary["summary_text"] if latest_summary else ""
    if prior_summary_text:
        conversation_text = (
            f"[PREVIOUS SUMMARY]\n{prior_summary_text}\n\n"
            f"[NEW MESSAGES]\n{_format_messages_for_summary(messages_to_summarise)}"
        )
    else:
        conversation_text = _format_messages_for_summary(messages_to_summarise)

    covered_up_to = messages_to_summarise[-1]["sequence"]

    # Try LLM summary; fall back to truncation summary on failure
    summary_text: Optional[str] = None
    if api_key and model_string:
        summary_text = await _call_llm_for_summary(conversation_text, api_key, model_string)

    if summary_text is None:
        # Fallback: truncate oldest messages into a placeholder summary
        # MEMORY.md: "Truncate oldest messages without summarisation on BYOK key failure."
        logger.info(
            "Compression fallback (no LLM): truncating for conversation %s", conversation_id
        )
        first_msg = messages_to_summarise[0]["content"][:100] if messages_to_summarise else ""
        summary_text = (
            f"[Auto-summary unavailable — {len(messages_to_summarise)} earlier messages truncated. "
            f"First message started: \"{first_msg}...\"]"
        )

    await _persist_summary(
        supabase,
        conversation_id=conversation_id,
        summary_text=summary_text,
        messages_covered_up_to=covered_up_to,
        model=model_string,
    )

    logger.info(
        "Compression complete for conversation %s: %d messages → summary (covered_up_to=%d)",
        conversation_id,
        len(messages_to_summarise),
        covered_up_to,
    )
    return True


def should_compress(message_count: int) -> bool:
    """Return True if message_count warrants a compression run."""
    return message_count > COMPRESSION_THRESHOLD
