"""
Conversations API routes — KIN-307, KIN-306, KIN-380.

Endpoints:
  POST   /api/v1/conversations                            — create a conversation (201)
  GET    /api/v1/conversations                            — list conversations, optional filters
  GET    /api/v1/conversations/{conversation_id}          — get a single conversation
  PATCH  /api/v1/conversations/{conversation_id}          — update title or active agent
  DELETE /api/v1/conversations/{conversation_id}          — soft-delete (204)
  GET    /api/v1/conversations/{conversation_id}/messages — list messages for a conversation
  POST   /api/v1/conversations/{conversation_id}/messages — store message + periodic proposal trigger
  POST   /api/v1/conversations/{conversation_id}/end      — fire conversation-end proposal bg job

Spec: docs/specs/kin-257-projects-conversations-spec.md §2, docs/specs/active-memory-spec.md
Schema: docs/db-schema-spec.md §5 (conversations), §6 (messages), §17 (memory_proposals),
        §19 (llm_models), §2 (user_api_keys)

Conventions:
  - Endpoint async fns use run_in_executor for all Supabase calls
  - Background jobs are sync (BackgroundTasks.add_task dispatches to thread pool)
  - Silent-skip policy: BYOK failure / no model / no messages → return without error
  - Never return None/[]/False on write operations — raise or log-and-raise
  - Periodic trigger debounce: skip dispatch if pending proposals already exist for conversation
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user
from app.core.errors import AuthorizationError, NotFoundError, ValidationError
from app.db.supabase_client import get_supabase
from app.services.background import TaskDispatcher
from app.services.encryption import decrypt_api_key, load_master_key
from app.services.llm_client import call_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])

# Prompt from active-memory-spec.md § Trigger 2
PROPOSAL_PROMPT = (
    "Review this conversation and identify 1–5 facts, decisions, preferences, or working patterns "
    "worth remembering in future sessions. Each entry should be a short, standalone sentence. "
    "Focus on things that would change how an AI collaborates with this person — not summaries "
    "of what was discussed.\n"
    "Format: return a JSON array of strings. Maximum 5 items. "
    "If nothing worth remembering, return []."
)


# ---------------------------------------------------------------------------
# Module-level accessors — defined here so tests can patch them
# ---------------------------------------------------------------------------


def get_supabase_client():
    """Return the service-role Supabase client. Defined at module level so tests can patch it."""
    return get_supabase()


def get_task_dispatcher(background_tasks: BackgroundTasks) -> TaskDispatcher:
    """Return a TaskDispatcher. Defined at module level so tests can patch it."""
    return TaskDispatcher(background_tasks)


# ---------------------------------------------------------------------------
# Background job
# ---------------------------------------------------------------------------


def _parse_proposals(text: str) -> list:
    """
    Parse LLM JSON response into a list of proposal strings.

    Strips markdown code fences, parses JSON array. Returns [] on any parse failure.
    """
    try:
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
        data = json.loads(cleaned)
        if isinstance(data, list):
            return [str(item) for item in data if isinstance(item, str) and item.strip()]
    except Exception as exc:
        logger.debug("_parse_proposals: parse failed: %s", exc)
    return []


def _to_bytes(val) -> bytes:
    """
    Convert a Supabase bytea field value to bytes.

    Supabase/PostgREST may return bytea columns as:
    - raw bytes (bytes/bytearray) — pass through
    - '\\x{hex}' prefixed hex string — strip prefix and decode
    - plain hex string (as stored by profile routes via .hex()) — decode directly
    """
    if isinstance(val, (bytes, bytearray)):
        return bytes(val)
    s = str(val)
    if s.startswith("\\x"):
        s = s[2:]
    return bytes.fromhex(s)


def _resolve_scope(
    client,
    project_id: Optional[str],
    active_agent_id: Optional[str],
    user_id: str,
    job_name: str,
) -> tuple:
    """
    Resolve conversation scope to (scope_col, scope_id) for memory_proposals rows.

    Returns (scope_col, scope_id) where scope_col is 'project_id' or 'agent_instance_id'.
    Returns (None, None) if no valid scope (company-level or agent_instance not found).

    Per spec §Trigger 1 scope resolution:
    - active_agent_id set → agent_instance scope (agent takes priority over project)
    - project_id set, no agent → project scope
    - neither → company-level conversation, no Active Memory
    """
    if active_agent_id:
        ai_res = (
            client.table("agent_instances")
            .select("id")
            .eq("agent_definition_id", active_agent_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not ai_res.data:
            logger.info(
                "%s: no agent_instance for agent %s / user %s, skipping",
                job_name,
                active_agent_id,
                user_id,
            )
            return None, None
        return "agent_instance_id", ai_res.data["id"]

    if project_id:
        return "project_id", project_id

    # Company-level conversation — no Active Memory (spec §Assumptions)
    logger.info("%s: no project or agent scope, skipping", job_name)
    return None, None


def _generate_proposals_job(conversation_id: str, user_id: str) -> None:
    """
    Background job: review full conversation with BYOK LLM → insert memory proposals.

    Silent-skip conditions (no error surfaced):
    - Conversation not found or no scope (project_id not set)
    - User has no default model
    - Default model not found in llm_models
    - No BYOK API key configured for that provider
    - Key decryption fails
    - No messages in conversation
    - LLM call fails
    - LLM returns no proposals

    Deduplication: case-insensitive comparison against existing pending proposals for scope.
    Appends new proposals; does not block when existing pending proposals exist.

    Schema refs:
    - conversations.project_id (scope)
    - users.default_model_id → llm_models.model_id + llm_models.provider
    - user_api_keys.provider + key_ciphertext + key_nonce
    - messages.role + content + sequence
    - memory_proposals: user_id, conversation_id, project_id, proposed_content, status, trigger_type
    """
    client = get_supabase_client()

    # 1. Fetch conversation — verify ownership, exclude soft-deleted, get scope
    conv_res = (
        client.table("conversations")
        .select("project_id, active_agent_id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    if not conv_res.data:
        logger.warning(
            "_generate_proposals_job: conversation %s not found for user %s",
            conversation_id,
            user_id,
        )
        return

    project_id = conv_res.data.get("project_id")
    active_agent_id = conv_res.data.get("active_agent_id")

    # Resolve scope: agent_instance > project > company-level (skip)
    scope_col, scope_id = _resolve_scope(
        client, project_id, active_agent_id, user_id, "_generate_proposals_job"
    )
    if scope_col is None:
        return

    # 2. Fetch user's default model ID
    user_res = (
        client.table("users")
        .select("default_model_id")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not user_res.data or not user_res.data.get("default_model_id"):
        logger.info(
            "_generate_proposals_job: no default model for user %s, skipping", user_id
        )
        return

    model_id = user_res.data["default_model_id"]

    # 3. Resolve model_id → model_id string + provider
    model_res = (
        client.table("llm_models")
        .select("model_id, provider")
        .eq("id", model_id)
        .single()
        .execute()
    )
    if not model_res.data:
        logger.info(
            "_generate_proposals_job: model %s not found in llm_models, skipping", model_id
        )
        return

    model_name: str = model_res.data["model_id"]  # e.g., "gpt-4o", "claude-sonnet-4-6"
    provider: str = model_res.data["provider"]     # e.g., "openai", "anthropic"

    # 4. Fetch BYOK key — silent skip if not configured
    key_res = (
        client.table("user_api_keys")
        .select("key_ciphertext, key_nonce")
        .eq("user_id", user_id)
        .eq("provider", provider)
        .single()
        .execute()
    )
    if not key_res.data:
        logger.info(
            "_generate_proposals_job: no BYOK key for provider %s, skipping", provider
        )
        return

    try:
        master_key = load_master_key()
        ciphertext = _to_bytes(key_res.data["key_ciphertext"])
        nonce = _to_bytes(key_res.data["key_nonce"])
        api_key = decrypt_api_key(ciphertext, nonce, master_key, user_id)
    except Exception as exc:
        logger.warning("_generate_proposals_job: key decryption failed: %s", exc)
        return

    # 5. Fetch full conversation messages
    msg_res = (
        client.table("messages")
        .select("role, content, sequence")
        .eq("conversation_id", conversation_id)
        .order("sequence")
        .execute()
    )
    chat_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in (msg_res.data or [])
        if m.get("role") in ("user", "assistant")
    ]
    if not chat_messages:
        logger.info(
            "_generate_proposals_job: no messages in conversation %s, skipping",
            conversation_id,
        )
        return

    chat_messages.append({"role": "user", "content": PROPOSAL_PROMPT})

    # 6. Call BYOK LLM — silent skip on failure
    try:
        response_text = call_llm(
            messages=chat_messages,
            model=model_name,
            api_key=api_key,
            max_tokens=512,
        )
    except Exception as exc:
        logger.warning("_generate_proposals_job: LLM call failed: %s", exc)
        return

    proposals = _parse_proposals(response_text)
    if not proposals:
        return

    # 7. Dedup against existing pending proposals for scope
    existing_res = (
        client.table("memory_proposals")
        .select("proposed_content")
        .eq("user_id", user_id)
        .eq(scope_col, scope_id)
        .eq("status", "pending")
        .execute()
    )
    existing_content: set = {
        r["proposed_content"].lower() for r in (existing_res.data or [])
    }

    # 8. Insert new proposals (append; skip content-level duplicates)
    for content in proposals:
        if content.lower() in existing_content:
            continue
        row = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            scope_col: scope_id,
            "proposed_content": content,
            "status": "pending",
            "trigger_type": "conversation_end",
        }
        try:
            client.table("memory_proposals").insert(row).execute()
        except Exception as exc:
            logger.error("_generate_proposals_job: insert failed: %s", exc)
            continue
        existing_content.add(content.lower())


# ---------------------------------------------------------------------------
# Periodic proposals background job (KIN-306)
# ---------------------------------------------------------------------------


def _generate_periodic_proposals_job(conversation_id: str, user_id: str) -> None:
    """
    Background job: review last 10 messages with BYOK LLM → insert periodic memory proposals.

    Same BYOK/silent-skip policy as _generate_proposals_job. Differences:
    - Uses only the most recent 10 messages (not full conversation)
    - trigger_type = 'periodic'
    - Content-level dedup against existing pending proposals for scope

    Spec: active-memory-spec.md § Trigger 3
    """
    client = get_supabase_client()

    # 1. Fetch conversation scope — exclude soft-deleted
    conv_res = (
        client.table("conversations")
        .select("project_id, active_agent_id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    if not conv_res.data:
        logger.warning(
            "_generate_periodic_proposals_job: conversation %s not found for user %s",
            conversation_id,
            user_id,
        )
        return

    project_id = conv_res.data.get("project_id")
    active_agent_id = conv_res.data.get("active_agent_id")

    # Resolve scope: agent_instance > project > company-level (skip)
    scope_col, scope_id = _resolve_scope(
        client, project_id, active_agent_id, user_id, "_generate_periodic_proposals_job"
    )
    if scope_col is None:
        return

    # 2. Fetch user's default model
    user_res = (
        client.table("users")
        .select("default_model_id")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not user_res.data or not user_res.data.get("default_model_id"):
        logger.info("_generate_periodic_proposals_job: no default model for user %s", user_id)
        return

    model_id = user_res.data["default_model_id"]
    model_res = (
        client.table("llm_models")
        .select("model_id, provider")
        .eq("id", model_id)
        .single()
        .execute()
    )
    if not model_res.data:
        logger.info("_generate_periodic_proposals_job: model %s not found, skipping", model_id)
        return

    model_name: str = model_res.data["model_id"]
    provider: str = model_res.data["provider"]

    # 3. Fetch BYOK key — silent skip if not configured
    key_res = (
        client.table("user_api_keys")
        .select("key_ciphertext, key_nonce")
        .eq("user_id", user_id)
        .eq("provider", provider)
        .single()
        .execute()
    )
    if not key_res.data:
        logger.info(
            "_generate_periodic_proposals_job: no BYOK key for provider %s, skipping", provider
        )
        return

    try:
        master_key = load_master_key()
        ciphertext = _to_bytes(key_res.data["key_ciphertext"])
        nonce = _to_bytes(key_res.data["key_nonce"])
        api_key = decrypt_api_key(ciphertext, nonce, master_key, user_id)
    except Exception as exc:
        logger.warning("_generate_periodic_proposals_job: key decryption failed: %s", exc)
        return

    # 4. Fetch last 10 messages (periodic trigger uses recent window only)
    msg_res = (
        client.table("messages")
        .select("role, content, sequence")
        .eq("conversation_id", conversation_id)
        .order("sequence")
        .execute()
    )
    # Slice to last 10 after sorting ascending
    recent = (msg_res.data or [])[-10:]
    chat_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in recent
        if m.get("role") in ("user", "assistant")
    ]
    if not chat_messages:
        logger.info(
            "_generate_periodic_proposals_job: no messages in conversation %s, skipping",
            conversation_id,
        )
        return

    chat_messages.append({"role": "user", "content": PROPOSAL_PROMPT})

    # 5. Call BYOK LLM — silent skip on failure
    try:
        response_text = call_llm(
            messages=chat_messages,
            model=model_name,
            api_key=api_key,
            max_tokens=512,
        )
    except Exception as exc:
        logger.warning("_generate_periodic_proposals_job: LLM call failed: %s", exc)
        return

    proposals = _parse_proposals(response_text)
    if not proposals:
        return

    # 6. Dedup against existing pending proposals for scope
    existing_res = (
        client.table("memory_proposals")
        .select("proposed_content")
        .eq("user_id", user_id)
        .eq(scope_col, scope_id)
        .eq("status", "pending")
        .execute()
    )
    existing_content: set = {
        r["proposed_content"].lower() for r in (existing_res.data or [])
    }

    # 7. Insert new proposals (append; skip content-level duplicates)
    for content in proposals:
        if content.lower() in existing_content:
            continue
        row = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            scope_col: scope_id,
            "proposed_content": content,
            "status": "pending",
            "trigger_type": "periodic",
        }
        try:
            client.table("memory_proposals").insert(row).execute()
        except Exception as exc:
            logger.error("_generate_periodic_proposals_job: insert failed: %s", exc)
            continue
        existing_content.add(content.lower())


# ---------------------------------------------------------------------------
# Rolling summary compression background job (KIN-392)
# ---------------------------------------------------------------------------

# Number of most-recent messages always kept in full (not summarized).
# MVP constant — dynamic budget calculation deferred until context token
# accounting is added to the assembler.
RECENT_TURNS_KEEP = 20

# Notification stored as a system message when compression fails and the context assembler
# falls back to naive truncation (KIN-393).
_TRUNCATION_NOTIFICATION = (
    "Conversation history was trimmed — your API key encountered an error."
)


def _insert_system_notification(client, conversation_id: str) -> None:
    """Append a role='system' notification message to the conversation message history.

    Called when rolling summary compression fails due to a BYOK or LLM error so that
    the UI can surface the event inline in the chat. Silent on insert failure.
    """
    try:
        seq_res = (
            client.table("messages")
            .select("sequence")
            .eq("conversation_id", conversation_id)
            .order("sequence", desc=True)
            .limit(1)
            .execute()
        )
        next_seq = (seq_res.data[0]["sequence"] + 1) if seq_res.data else 0
        client.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "system",
            "content": _TRUNCATION_NOTIFICATION,
            "sequence": next_seq,
        }).execute()
        logger.info(
            "_insert_system_notification: inserted for conversation %s", conversation_id
        )
    except Exception as exc:
        logger.warning(
            "_insert_system_notification: failed for conversation %s: %s",
            conversation_id,
            exc,
        )


def _generate_summary_job(conversation_id: str, user_id: str) -> None:
    """
    Background job: generate rolling summary for conversation history compression.

    Triggered every 10 messages. Summarizes all messages except the most recent
    RECENT_TURNS_KEEP turns into a condensed paragraph and stores a new row in
    conversation_summaries.

    Incremental approach: if a prior summary exists, folds it + new messages
    together (more efficient than re-summarizing from scratch).

    Silent-skip conditions (same BYOK/silent-skip policy as other bg jobs):
    - Fewer than RECENT_TURNS_KEEP + 1 valid messages (nothing to summarize)
    - Summary already covers all messages up to target boundary
    - No default model configured for user
    - No BYOK API key for the provider
    - Key decryption fails
    - LLM call fails

    Schema refs:
    - conversations: verify ownership + scope
    - conversation_summaries: messages_covered_up_to (last summarized sequence)
    - messages: role + content + sequence
    - users.default_model_id → llm_models.model_id + provider
    - user_api_keys: key_ciphertext + key_nonce

    Ticket: KIN-392
    """
    from app.services.prompts import get_prompt

    client = get_supabase_client()

    # 1. Verify conversation ownership
    conv_res = (
        client.table("conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    if not conv_res.data:
        logger.warning(
            "_generate_summary_job: conversation %s not found for user %s",
            conversation_id,
            user_id,
        )
        return

    # 2. Fetch all messages ordered by sequence
    msg_res = (
        client.table("messages")
        .select("role, content, sequence")
        .eq("conversation_id", conversation_id)
        .order("sequence")
        .execute()
    )
    all_messages = [
        m for m in (msg_res.data or [])
        if m.get("role") in ("user", "assistant")
    ]
    if len(all_messages) <= RECENT_TURNS_KEEP:
        # Nothing to summarize — all messages fit in the recent window
        logger.info(
            "_generate_summary_job: only %d messages, nothing to compress (threshold %d)",
            len(all_messages),
            RECENT_TURNS_KEEP,
        )
        return

    # Messages to summarize: everything except the last RECENT_TURNS_KEEP
    messages_to_summarize = all_messages[:-RECENT_TURNS_KEEP]
    target_covered_up_to = messages_to_summarize[-1]["sequence"]

    # 3. Fetch latest existing summary
    sum_res = (
        client.table("conversation_summaries")
        .select("summary_text, messages_covered_up_to")
        .eq("conversation_id", conversation_id)
        .order("messages_covered_up_to", desc=True)
        .limit(1)
        .execute()
    )
    prior_summary = sum_res.data[0] if sum_res.data else None

    # Skip if summary is already current
    if prior_summary and prior_summary["messages_covered_up_to"] >= target_covered_up_to:
        logger.info(
            "_generate_summary_job: summary already current (covered_up_to=%d, target=%d)",
            prior_summary["messages_covered_up_to"],
            target_covered_up_to,
        )
        return

    # 4. Resolve BYOK key
    user_res = (
        client.table("users")
        .select("default_model_id")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not user_res.data or not user_res.data.get("default_model_id"):
        logger.info("_generate_summary_job: no default model for user %s, skipping", user_id)
        return

    model_id = user_res.data["default_model_id"]
    model_res = (
        client.table("llm_models")
        .select("model_id, provider")
        .eq("id", model_id)
        .single()
        .execute()
    )
    if not model_res.data:
        logger.info("_generate_summary_job: model %s not found in llm_models, skipping", model_id)
        return

    model_name: str = model_res.data["model_id"]
    provider: str = model_res.data["provider"]

    key_res = (
        client.table("user_api_keys")
        .select("key_ciphertext, key_nonce")
        .eq("user_id", user_id)
        .eq("provider", provider)
        .single()
        .execute()
    )
    if not key_res.data:
        logger.info(
            "_generate_summary_job: no BYOK key for provider %s, skipping", provider
        )
        _insert_system_notification(client, conversation_id)
        return

    try:
        master_key = load_master_key()
        ciphertext = _to_bytes(key_res.data["key_ciphertext"])
        nonce = _to_bytes(key_res.data["key_nonce"])
        api_key = decrypt_api_key(ciphertext, nonce, master_key, user_id)
    except Exception as exc:
        logger.warning("_generate_summary_job: key decryption failed: %s", exc)
        _insert_system_notification(client, conversation_id)
        return

    # 5. Build LLM prompt
    if prior_summary:
        # Incremental: fold prior summary + new messages since last covered sequence
        new_messages = [
            m for m in messages_to_summarize
            if m["sequence"] > prior_summary["messages_covered_up_to"]
        ]
        if not new_messages:
            logger.info(
                "_generate_summary_job: no new messages to incorporate for conversation %s",
                conversation_id,
            )
            return
        prompt_text = get_prompt("conversation-summary-v1", "summarize_incremental")
        conversation_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in new_messages
        )
        llm_messages = [
            {
                "role": "user",
                "content": (
                    f"{prompt_text}\n\n"
                    f"Previous summary:\n{prior_summary['summary_text']}\n\n"
                    f"New messages:\n{conversation_text}"
                ),
            }
        ]
    else:
        # Fresh summary from scratch
        prompt_text = get_prompt("conversation-summary-v1", "summarize_new")
        conversation_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages_to_summarize
        )
        llm_messages = [
            {
                "role": "user",
                "content": f"{prompt_text}\n\nConversation:\n{conversation_text}",
            }
        ]

    # 6. Call BYOK LLM — fall back to truncation + notification on failure (KIN-393)
    try:
        summary_text = call_llm(
            messages=llm_messages,
            model=model_name,
            api_key=api_key,
            max_tokens=600,
        )
    except Exception as exc:
        logger.warning("_generate_summary_job: LLM call failed: %s", exc)
        _insert_system_notification(client, conversation_id)
        return

    summary_text = summary_text.strip()
    if not summary_text:
        logger.info("_generate_summary_job: LLM returned empty summary, skipping")
        return

    # 7. Insert new summary row (append-only per schema)
    row = {
        "conversation_id": conversation_id,
        "summary_text": summary_text,
        "messages_covered_up_to": target_covered_up_to,
        "model": model_name,
    }
    try:
        client.table("conversation_summaries").insert(row).execute()
        logger.info(
            "_generate_summary_job: summary stored for conversation %s (covered_up_to=%d)",
            conversation_id,
            target_covered_up_to,
        )
    except Exception as exc:
        logger.error("_generate_summary_job: insert failed: %s", exc)


# ---------------------------------------------------------------------------
# Title generation background job (KIN-389)
# ---------------------------------------------------------------------------

TITLE_PROMPT = (
    "Generate a concise conversation title (max 6 words) for this message. "
    "Return ONLY the title text, no quotes, no punctuation at the end."
)


def _generate_title_job(conversation_id: str, user_id: str, user_message: str) -> None:
    """
    Background job: auto-generate a conversation title from the first user message.

    Uses the user's BYOK default model. Silent-skip on any failure — title stays null
    and the UI renders "New conversation".

    Spec: PRD §5 — "Auto-generated from first message; user can rename."
    MEMORY.md: "Conversation title generation uses BYOK key (user's default model)."
    """
    client = get_supabase_client()

    # Check if conversation already has a title (user may have set one at creation)
    conv_res = (
        client.table("conversations")
        .select("title")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    if not conv_res.data:
        return
    if conv_res.data.get("title"):
        logger.info("_generate_title_job: conversation %s already has title, skipping", conversation_id)
        return

    # Resolve BYOK key (same pattern as _generate_proposals_job)
    user_res = (
        client.table("users")
        .select("default_model_id")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not user_res.data or not user_res.data.get("default_model_id"):
        logger.info("_generate_title_job: no default model for user %s, skipping", user_id)
        return

    model_id = user_res.data["default_model_id"]
    model_res = (
        client.table("llm_models")
        .select("model_id, provider")
        .eq("id", model_id)
        .single()
        .execute()
    )
    if not model_res.data:
        return

    model_name: str = model_res.data["model_id"]
    provider: str = model_res.data["provider"]

    key_res = (
        client.table("user_api_keys")
        .select("key_ciphertext, key_nonce")
        .eq("user_id", user_id)
        .eq("provider", provider)
        .single()
        .execute()
    )
    if not key_res.data:
        logger.info("_generate_title_job: no BYOK key for provider %s, skipping", provider)
        return

    try:
        master_key = load_master_key()
        ciphertext = _to_bytes(key_res.data["key_ciphertext"])
        nonce = _to_bytes(key_res.data["key_nonce"])
        api_key = decrypt_api_key(ciphertext, nonce, master_key, user_id)
    except Exception as exc:
        logger.warning("_generate_title_job: key decryption failed: %s", exc)
        return

    # Generate title
    try:
        title = call_llm(
            messages=[
                {"role": "user", "content": f"{TITLE_PROMPT}\n\nMessage: {user_message}"},
            ],
            model=model_name,
            api_key=api_key,
            max_tokens=30,
        )
    except Exception as exc:
        logger.warning("_generate_title_job: LLM call failed: %s", exc)
        return

    title = title.strip().strip('"').strip("'")[:100]  # Clean and cap at 100 chars
    if not title:
        return

    # Update conversation title
    try:
        client.table("conversations").update({"title": title}).eq("id", conversation_id).eq("user_id", user_id).execute()
        logger.info("_generate_title_job: set title for conversation %s: %s", conversation_id, title)
    except Exception as exc:
        logger.error("_generate_title_job: failed to update title: %s", exc)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CreateConversationRequest(BaseModel):
    company_id: str
    project_id: Optional[str] = None
    title: Optional[str] = None
    active_agent_id: Optional[str] = None


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    active_agent_id: Optional[str] = None


class StoreMessageRequest(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    agent_definition_id: Optional[str] = None
    model: Optional[str] = None

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("content must not be empty")
        return v


# ---------------------------------------------------------------------------
# CRUD Endpoints — KIN-380
# ---------------------------------------------------------------------------


async def _verify_company_ownership(company_id: str, user_id: str, client) -> None:
    """Verify the company belongs to the requesting user."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("companies")
            .select("id")
            .eq("id", company_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute(),
    )
    if not result.data:
        raise AuthorizationError("Company does not belong to the requesting user")


@router.post("", status_code=201)
async def create_conversation(
    body: CreateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Create a new conversation.

    Verifies company ownership. If project_id provided, verifies the project belongs to user
    and the company. Sets user_id from auth.

    Raises:
        AuthorizationError (403): company_id or project_id does not belong to the user.
        ValidationError (400): DB returned no data after insert.
    """
    client = get_supabase_client()
    await _verify_company_ownership(body.company_id, current_user.user_id, client)

    loop = asyncio.get_running_loop()

    # If project_id provided, verify project ownership and company match
    if body.project_id:
        proj_res = await loop.run_in_executor(
            None,
            lambda: client.table("projects")
                .select("id, company_id")
                .eq("id", body.project_id)
                .eq("user_id", current_user.user_id)
                .single()
                .execute(),
        )
        if not proj_res.data:
            raise NotFoundError("Project not found")
        if proj_res.data["company_id"] != body.company_id:
            raise ValidationError("Project does not belong to the specified company")

    row = {
        "user_id": current_user.user_id,
        "company_id": body.company_id,
        "project_id": body.project_id,
        "title": body.title,
        "active_agent_id": body.active_agent_id,
    }

    result = await loop.run_in_executor(
        None,
        lambda: client.table("conversations").insert(row).execute(),
    )
    if not result.data:
        logger.error(
            "create_conversation: no data returned from insert",
            extra={"user_id": current_user.user_id, "company_id": body.company_id},
        )
        raise ValidationError("Failed to create conversation")
    return result.data[0]


CONVERSATION_SELECT = (
    "id, user_id, company_id, project_id, title, active_agent_id, "
    "deleted_at, created_at, updated_at"
)


@router.get("")
async def list_conversations(
    company_id: Optional[str] = Query(default=None),
    project_id: Optional[str] = Query(default=None),
    agent_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List the current user's conversations, ordered by most-recently-updated first.

    Filters (all optional, combinable):
      - company_id: conversations in this company
      - project_id: conversations in this project
      - agent_id: conversations with this agent active

    Excludes soft-deleted conversations. Enriches each conversation with
    project_name and agent_name for sidebar display.

    Raises:
        AuthorizationError (403): company_id does not belong to the user.
    """
    client = get_supabase_client()
    loop = asyncio.get_running_loop()

    if company_id:
        await _verify_company_ownership(company_id, current_user.user_id, client)

    # Build query
    def _run_query():
        q = (
            client.table("conversations")
            .select(CONVERSATION_SELECT)
            .eq("user_id", current_user.user_id)
            .is_("deleted_at", "null")
            .order("updated_at", desc=True)
            .limit(limit)
        )
        if company_id:
            q = q.eq("company_id", company_id)
        if project_id:
            q = q.eq("project_id", project_id)
        if agent_id:
            q = q.eq("active_agent_id", agent_id)
        return q.execute()

    result = await loop.run_in_executor(None, _run_query)
    conversations = result.data or []

    # Enrich with project_name and agent_name for sidebar display
    project_ids = {c["project_id"] for c in conversations if c.get("project_id")}
    agent_ids = {c["active_agent_id"] for c in conversations if c.get("active_agent_id")}

    project_names: dict = {}
    agent_names: dict = {}

    if project_ids:
        proj_res = await loop.run_in_executor(
            None,
            lambda: client.table("projects")
                .select("id, name")
                .in_("id", list(project_ids))
                .execute(),
        )
        project_names = {p["id"]: p["name"] for p in (proj_res.data or [])}

    if agent_ids:
        agent_res = await loop.run_in_executor(
            None,
            lambda: client.table("agent_definitions")
                .select("id, name")
                .in_("id", list(agent_ids))
                .execute(),
        )
        agent_names = {a["id"]: a["name"] for a in (agent_res.data or [])}

    for conv in conversations:
        conv["project_name"] = project_names.get(conv.get("project_id"))
        conv["agent_name"] = agent_names.get(conv.get("active_agent_id"))

    return {"conversations": conversations}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Get a single conversation by ID.

    Raises:
        NotFoundError (404): Conversation not found or not owned by current user.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client.table("conversations")
            .select(CONVERSATION_SELECT)
            .eq("id", conversation_id)
            .eq("user_id", current_user.user_id)
            .is_("deleted_at", "null")
            .single()
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Conversation not found")
    return result.data


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    body: UpdateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update a conversation's title or active agent.

    Raises:
        NotFoundError (404): Conversation not found or not owned by current user.
    """
    client = get_supabase_client()
    loop = asyncio.get_running_loop()

    updates: dict = {}
    if body.title is not None:
        updates["title"] = body.title
    if body.active_agent_id is not None:
        updates["active_agent_id"] = body.active_agent_id

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = await loop.run_in_executor(
        None,
        lambda: client.table("conversations")
            .update(updates)
            .eq("id", conversation_id)
            .eq("user_id", current_user.user_id)
            .is_("deleted_at", "null")
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Conversation not found")
    return result.data[0]


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """
    Soft-delete a conversation (sets deleted_at).

    Raises:
        NotFoundError (404): Conversation not found or not owned by current user.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client.table("conversations")
            .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", conversation_id)
            .eq("user_id", current_user.user_id)
            .is_("deleted_at", "null")
            .execute(),
    )
    if not result.data:
        raise NotFoundError("Conversation not found")


# ---------------------------------------------------------------------------
# Message + Proposal Endpoints
# ---------------------------------------------------------------------------


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List messages for a conversation, ordered by sequence.

    Returns { messages: [...] } where each message has id, role, content, model,
    sequence, and created_at.

    Schema: docs/db-schema-spec.md §6 (messages)
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Verify conversation ownership
    conv_res = await loop.run_in_executor(
        None,
        lambda: client.table("conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", current_user.user_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute(),
    )
    if not conv_res.data:
        raise NotFoundError("Conversation not found")

    msg_res = await loop.run_in_executor(
        None,
        lambda: client.table("messages")
        .select("id, role, content, model, sequence, created_at")
        .eq("conversation_id", conversation_id)
        .order("sequence")
        .execute(),
    )

    return {"messages": msg_res.data or []}


@router.post("/{conversation_id}/messages", status_code=201)
async def store_message(
    conversation_id: str,
    body: StoreMessageRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Store a message in a conversation.

    After every 10th message (message_count % 10 == 0), dispatches a non-blocking background
    job to generate periodic memory proposals via the user's BYOK LLM.

    Debounce: if pending proposals already exist for this conversation, the periodic
    job is NOT dispatched again (avoids duplicate batches).

    Returns 201 with the stored message row.

    Spec: active-memory-spec.md § Trigger 3
    Schema: docs/db-schema-spec.md §6 (messages)
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Verify conversation ownership — exclude soft-deleted conversations
    conv_res = await loop.run_in_executor(
        None,
        lambda: client.table("conversations")
        .select("id, project_id")
        .eq("id", conversation_id)
        .eq("user_id", current_user.user_id)
        .is_("deleted_at", "null")
        .single()
        .execute(),
    )
    if not conv_res.data:
        raise NotFoundError("Conversation not found")

    # Count existing messages (determines sequence + whether 10th-message fires)
    count_res = await loop.run_in_executor(
        None,
        lambda: client.table("messages")
        .select("id")
        .eq("conversation_id", conversation_id)
        .execute(),
    )
    current_count = len(count_res.data or [])

    # Build and insert message row
    row: dict = {
        "conversation_id": conversation_id,
        "role": body.role,
        "content": body.content,
        "sequence": current_count,  # 0-indexed; sequence == current_count before insert
    }
    if body.agent_definition_id:
        row["agent_definition_id"] = body.agent_definition_id
    if body.model:
        row["model"] = body.model

    insert_res = await loop.run_in_executor(
        None,
        lambda: client.table("messages").insert(row).execute(),
    )
    if not insert_res.data:
        raise ValidationError("Failed to store message")

    message = insert_res.data[0]

    # Periodic proposal trigger — every 10th message, debounced on pending proposals
    new_count = current_count + 1
    if new_count % 10 == 0:
        pending_res = await loop.run_in_executor(
            None,
            lambda: client.table("memory_proposals")
            .select("id")
            .eq("conversation_id", conversation_id)
            .eq("status", "pending")
            .execute(),
        )
        if not (pending_res.data):
            dispatcher = get_task_dispatcher(background_tasks)
            dispatcher.dispatch(
                _generate_periodic_proposals_job, conversation_id, current_user.user_id
            )

    return message


@router.post("/{conversation_id}/end", status_code=202)
async def end_conversation(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Signal that a conversation has ended.

    Immediately returns 202. Dispatches a non-blocking background job that:
    - Fetches the full conversation
    - Calls the user's BYOK default LLM to generate memory proposals
    - Inserts proposals into memory_proposals with trigger_type='conversation_end'

    Silent-skip policy: if no BYOK key is configured, the model is missing, or the LLM
    call fails, the background job returns without error. No error is surfaced to the caller.

    Spec: active-memory-spec.md § Trigger 2
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Verify conversation ownership — exclude soft-deleted conversations (KIN-344)
    conv_res = await loop.run_in_executor(
        None,
        lambda: client.table("conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", current_user.user_id)
        .is_("deleted_at", "null")
        .single()
        .execute(),
    )
    if not conv_res.data:
        raise NotFoundError("Conversation not found")

    dispatcher = get_task_dispatcher(background_tasks)
    dispatcher.dispatch(_generate_proposals_job, conversation_id, current_user.user_id)
    return {"status": "accepted"}
