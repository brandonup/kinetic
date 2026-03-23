"""
Conversation compression service — ADR-004.

Fires when user message count exceeds COMPRESSION_THRESHOLD (20).
Produces a rolling summary of all messages not yet covered, then stores it
in conversation_summaries. Future context assembly injects: summary + verbatim window.

Entry point: compress_conversation(supabase, conv_id, user_id, model_string, byok_key)

ADR ref: docs/adr-004-conversation-compression.md
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT_TEMPLATE = """\
You are summarizing a conversation to preserve key context while reducing token usage.

Conversation so far:
{messages_text}

Write a concise summary (3-6 sentences) that captures:
- The main topics discussed
- Key decisions or conclusions reached
- Important context a future assistant should know

Respond with ONLY the summary text, no preamble.
"""


async def compress_conversation(
    *,
    supabase: Any,
    conv_id: str,
    user_id: str,
    model_string: str,
    byok_key: str,
) -> None:
    """Generate and store a rolling summary for a conversation.

    Idempotent: will not re-summarize messages already covered by the most-recent summary.
    """
    import asyncio

    from app.config import get_settings
    from app.services.llm_client import complete

    settings = get_settings()
    loop = asyncio.get_running_loop()

    async def db(fn: Any) -> Any:
        return await loop.run_in_executor(None, fn)

    # Check most-recent summary to avoid re-summarizing covered messages
    summary_result = await db(
        lambda: supabase.table("conversation_summaries")
        .select("messages_covered_up_to")
        .eq("conversation_id", conv_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    covered_up_to: int = 0
    if summary_result.data:
        covered_up_to = summary_result.data[0].get("messages_covered_up_to", 0)

    # Fetch messages not yet covered (exclude the verbatim window from end)
    all_msgs_result = await db(
        lambda: supabase.table("messages")
        .select("role, content, sequence")
        .eq("conversation_id", conv_id)
        .in_("role", ["user", "assistant"])
        .order("sequence", desc=False)
        .execute()
    )
    all_messages: list[dict] = all_msgs_result.data or []

    # Only messages after the already-covered point
    uncovered = [m for m in all_messages if m["sequence"] > covered_up_to]

    # Keep verbatim window intact — only summarize messages before it
    verbatim_count = settings.VERBATIM_WINDOW
    if len(uncovered) <= verbatim_count:
        # Nothing new to summarize (all messages within verbatim window)
        return

    to_summarize = uncovered[:-verbatim_count]
    if not to_summarize:
        return

    # Build messages text for the prompt
    lines: list[str] = []
    for m in to_summarize:
        role_label = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{role_label}: {m['content']}")

    messages_text = "\n\n".join(lines)
    prompt = _SUMMARY_PROMPT_TEMPLATE.format(messages_text=messages_text)

    try:
        summary_text = await complete(
            messages=[{"role": "user", "content": prompt}],
            model=model_string,
            api_key=byok_key,
            max_tokens=512,
        )
    except Exception:
        logger.exception("LLM call for compression failed for conv %s", conv_id)
        return

    if not summary_text or not summary_text.strip():
        return

    # The summary covers up to the last message in to_summarize
    new_covered_up_to: int = to_summarize[-1]["sequence"]

    try:
        await db(
            lambda: supabase.table("conversation_summaries")
            .insert(
                {
                    "conversation_id": conv_id,
                    "summary_text": summary_text.strip(),
                    "messages_covered_up_to": new_covered_up_to,
                }
            )
            .execute()
        )
        logger.info(
            "Compressed conversation %s: summary covers up to sequence %d",
            conv_id,
            new_covered_up_to,
        )
    except Exception:
        logger.exception("Failed to store summary for conv %s", conv_id)
