"""
Admin Prompt Debug API route — KIN-419.

Endpoint:
  GET /api/v1/admin/messages/{message_id}/prompt — full assembled prompt for a message (admin only)

Returns the complete messages array (system + history + user turn) that was sent
to the LLM for a given assistant message. Only populated on assistant messages
that have debug_prompt stored.

Schema ref: docs/db-schema-spec.md §6 (messages)
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends

from app.auth.deps import CurrentUser, require_admin
from app.core.errors import NotFoundError
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/messages", tags=["admin-prompt-debug"])


# ---------------------------------------------------------------------------
# Module-level accessor — allows tests to patch the supabase client
# ---------------------------------------------------------------------------


def get_supabase_client():
    """Return the service-role Supabase client. Defined at module level so tests can patch it."""
    return get_supabase()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/{message_id}/prompt")
async def get_message_prompt(
    message_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    Return the full assembled prompt for a given assistant message (admin only).

    The debug_prompt field contains the complete messages array sent to the LLM:
      - messages[0]: system message (L1–L9 assembled context stack)
      - messages[1..n-1]: conversation history
      - messages[n]: current user turn

    Response includes:
      - message_id: the message UUID
      - model: model string used for generation
      - debug_prompt: the full messages array
      - prompt_size_chars: total character count across all message contents
      - message_count: number of messages in the prompt array

    Raises:
        NotFoundError (404): Message not found or debug_prompt is null.
        AuthorizationError (403): Non-admin caller.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    try:
        result = await loop.run_in_executor(
            None,
            lambda: client
                .table("messages")
                .select("id, model, debug_prompt, role, conversation_id")
                .eq("id", message_id)
                .single()
                .execute(),
        )
    except Exception as exc:
        logger.error("get_message_prompt: failed to fetch message %s: %s", message_id, exc)
        raise NotFoundError("Message not found")

    if not result.data:
        raise NotFoundError("Message not found")

    row = result.data
    debug_prompt = row.get("debug_prompt")

    if debug_prompt is None:
        raise NotFoundError("No prompt data available for this message")

    # Compute prompt size metrics
    prompt_size_chars = sum(
        len(msg.get("content", "")) for msg in debug_prompt
    )

    return {
        "message_id": row["id"],
        "conversation_id": row["conversation_id"],
        "model": row.get("model"),
        "role": row["role"],
        "debug_prompt": debug_prompt,
        "prompt_size_chars": prompt_size_chars,
        "message_count": len(debug_prompt),
    }
