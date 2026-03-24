"""
Conversations API routes — KIN-307, KIN-306.

Endpoints:
  POST /api/v1/conversations/{conversation_id}/messages — store message + periodic proposal trigger
  POST /api/v1/conversations/{conversation_id}/end     — fire conversation-end proposal bg job

Spec: docs/specs/active-memory-spec.md
  § Trigger 2 (AI-Proposed at Conversation End) — KIN-307
  § Trigger 3 (Periodic Background Proposals)   — KIN-306
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
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user
from app.core.errors import NotFoundError, ValidationError
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
# Pydantic models
# ---------------------------------------------------------------------------


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
# Endpoints
# ---------------------------------------------------------------------------


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
