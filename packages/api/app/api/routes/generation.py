"""
Generation endpoint — KIN-276.

POST /api/v1/conversations/{conversation_id}/messages

Receives a user message, assembles context, routes to LLM via LiteLLM,
streams the response via SSE, persists both messages.

Spec ref: docs/specs/kin-257-projects-conversations-spec.md §2.3
ADR ref: docs/adr-003-agents-architecture.md (SSE protocol, BYOK routing, persistence order)
Schema ref: docs/db-schema-spec.md §5 (conversations), §6 (messages)
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any, AsyncGenerator, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.core.errors import (
    ForbiddenError,
    NotFoundError,
    PaymentRequiredError,
    ServiceUnavailableError,
    ValidationError,
)
from app.db import get_supabase_client
from app.services import compression as compression_service
from app.services import context_stack as context_stack_service
from app.services.encryption import decrypt
from app.services.task_dispatcher import FastAPITaskDispatcher

try:
    import litellm  # type: ignore  # noqa: F401
except ImportError:  # pragma: no cover
    litellm = None  # type: ignore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conversations", tags=["generation"])

# ---------------------------------------------------------------------------
# Provider → LiteLLM prefix mapping
# ---------------------------------------------------------------------------

_PROVIDER_PREFIX: dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "google",
    "groq": "groq",
}


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class SendMessageRequest(BaseModel):
    content: str
    model_id: Optional[UUID] = None  # UUID ref to llm_models.id; None = user default


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _fetch_conversation(supabase: Any, conv_id: str, user_id: str) -> dict:
    result = await _run(
        lambda: supabase.table("conversations")
        .select("id, company_id, project_id, active_agent_id, title, user_id")
        .eq("id", conv_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise NotFoundError("Conversation not found")
    return result.data


async def _fetch_model_row(supabase: Any, model_id: str) -> dict:
    result = await _run(
        lambda: supabase.table("llm_models")
        .select("id, provider, model_id, context_window, display_name")
        .eq("id", model_id)
        .eq("enabled", True)
        .eq("category", "generation")
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise ValidationError("Model not found or not enabled")
    return result.data


async def _fetch_user_default_model_id(supabase: Any, user_id: str) -> Optional[str]:
    result = await _run(
        lambda: supabase.table("users")
        .select("default_model_id")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if result.data:
        return result.data.get("default_model_id")
    return None


async def _fetch_byok_key(
    supabase: Any, user_id: str, provider: str
) -> Optional[str]:
    """Fetch and decrypt the user's API key for the given provider."""
    result = await _run(
        lambda: supabase.table("user_api_keys")
        .select("key_ciphertext, key_nonce")
        .eq("user_id", user_id)
        .eq("provider", provider)
        .maybe_single()
        .execute()
    )
    if not result.data:
        return None
    try:
        return decrypt(
            result.data["key_ciphertext"],
            result.data["key_nonce"],
        )
    except Exception as exc:
        logger.warning("Failed to decrypt API key for user %s / %s: %s", user_id, provider, exc)
        return None


async def _get_next_sequence(supabase: Any, conv_id: str) -> int:
    result = await _run(
        lambda: supabase.table("messages")
        .select("sequence")
        .eq("conversation_id", conv_id)
        .order("sequence", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return (rows[0]["sequence"] + 1) if rows else 0


async def _insert_message(
    supabase: Any,
    conv_id: str,
    role: str,
    content: str,
    sequence: int,
    *,
    model: Optional[str] = None,
    agent_definition_id: Optional[str] = None,
) -> dict:
    row: dict = {
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "sequence": sequence,
        "model": model,
        "agent_definition_id": agent_definition_id,
    }
    result = await _run(
        lambda: supabase.table("messages").insert(row).execute()
    )
    if not result.data:
        raise ValidationError(f"Failed to persist {role} message")
    return result.data[0]


async def _count_messages(supabase: Any, conv_id: str) -> int:
    result = await _run(
        lambda: supabase.table("messages")
        .select("id", count="exact")
        .eq("conversation_id", conv_id)
        .execute()
    )
    return result.count or 0


async def _bump_updated_at(supabase: Any, conv_id: str) -> None:
    await _run(
        lambda: supabase.table("conversations")
        .update({"updated_at": datetime.datetime.utcnow().isoformat()})
        .eq("id", conv_id)
        .execute()
    )


# ---------------------------------------------------------------------------
# Background job stubs
# ---------------------------------------------------------------------------


async def _generate_title(
    supabase: Any,
    conv_id: str,
    first_message: str,
    api_key: str,
    model_string: str,
) -> None:
    """
    Generate a short conversation title from the first user message.

    Decision ref: MEMORY.md 2026-03-22 — "Conversation title generation uses
    BYOK key (user's default model). If no key configured, title stays null."
    """
    try:
        prompt = (
            f"Generate a short, descriptive title (4-7 words) for a conversation "
            f"that starts with this message. Return ONLY the title, no quotes or punctuation.\n\n"
            f"Message: {first_message[:500]}"
        )
        response = await litellm.acompletion(
            model=model_string,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.5,
            api_key=api_key,
        )
        title = response.choices[0].message.content.strip()[:120]
        if title:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: supabase.table("conversations")
                .update({"title": title})
                .eq("id", conv_id)
                .execute(),
            )
    except Exception as exc:
        logger.warning("Title generation failed for conversation %s: %s", conv_id, exc)


async def _stub_memory_proposal(conv_id: str) -> None:
    """
    Memory proposal trigger stub.

    Decision ref: MEMORY.md 2026-03-21 — "Active Memory write UX: triple-trigger —
    user-initiated, AI-proposed at explicit conversation end, periodic background
    generation every N messages."
    Full implementation deferred to Sprint 5.
    """
    # TODO Sprint 5: implement memory proposal generation
    logger.debug("Memory proposal stub triggered for conversation %s (Sprint 5)", conv_id)


# ---------------------------------------------------------------------------
# LiteLLM helpers
# ---------------------------------------------------------------------------


def _litellm_model_string(model_row: dict) -> str:
    """Build the LiteLLM model string from a llm_models row."""
    provider = model_row["provider"]
    model_id = model_row["model_id"]
    prefix = _PROVIDER_PREFIX.get(provider, provider)
    return f"{prefix}/{model_id}"


def _build_llm_messages(
    context: context_stack_service.ContextStack,
    current_content: str,
) -> list[dict]:
    """Build the full messages array for the LiteLLM call."""
    messages: list[dict] = []
    if context.system_prompt:
        messages.append({"role": "system", "content": context.system_prompt})
    messages.extend(context.history)
    messages.append({"role": "user", "content": current_content})
    return messages


# ---------------------------------------------------------------------------
# SSE streaming generator
# ---------------------------------------------------------------------------


async def _stream_response(
    supabase: Any,
    conv_id: str,
    current_content: str,
    model_row: dict,
    api_key: str,
    user_msg_sequence: int,
    active_agent_id: Optional[str],
    background_tasks: BackgroundTasks,
    user_id: str,
    conv_title: Optional[str],
) -> AsyncGenerator[str, None]:
    """
    Core async generator that:
    1. Assembles context (fetched here, after user msg is persisted)
    2. Calls LiteLLM with stream=True
    3. Yields SSE deltas
    4. On completion: persists assistant message + triggers background jobs
    """
    full_response: list[str] = []
    model_string = _litellm_model_string(model_row)

    try:
        # Assemble context stack (L1-L9 per KIN-275)
        context = await context_stack_service.assemble(
            conv_id,
            user_id,
            supabase,
            query=current_content,
        )

        messages = _build_llm_messages(context, current_content)

        stream = await litellm.acompletion(
            model=model_string,
            messages=messages,
            stream=True,
            api_key=api_key,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full_response.append(delta)
                yield f"data: {json.dumps({'delta': delta})}\n\n"

    except Exception as exc:
        provider_msg = str(exc)
        logger.error("LLM generation error for conversation %s: %s", conv_id, exc)
        yield f"data: {json.dumps({'error': provider_msg})}\n\n"
        # Don't persist a failed assistant message
        return

    # Persist assistant message BEFORE sending done (so client can rely on it being saved)
    assistant_content = "".join(full_response)
    assistant_seq = user_msg_sequence + 1
    try:
        await _insert_message(
            supabase,
            conv_id,
            "assistant",
            assistant_content,
            assistant_seq,
            model=model_row["model_id"],
            agent_definition_id=active_agent_id,
        )
        await _bump_updated_at(supabase, conv_id)
    except Exception as exc:
        logger.error("Failed to persist assistant message: %s", exc)

    # Terminal SSE event
    yield f"data: {json.dumps({'done': True})}\n\n"

    # ---------------------------------------------------------------------------
    # Background jobs (non-blocking)
    # ---------------------------------------------------------------------------
    dispatcher = FastAPITaskDispatcher(background_tasks)
    msg_count = await _count_messages(supabase, conv_id)

    # Title generation — first user message, no title yet
    if msg_count <= 2 and not conv_title and api_key:
        dispatcher.dispatch(
            _generate_title,
            supabase,
            conv_id,
            current_content,
            api_key,
            model_string,
        )

    # Memory proposal — every 10 messages (MEMORY.md: MEMORY_PROPOSAL_INTERVAL=10)
    if msg_count % 10 == 0:
        dispatcher.dispatch(_stub_memory_proposal, conv_id)

    # Compression — when message count exceeds threshold
    if compression_service.should_compress(msg_count):
        dispatcher.dispatch(
            compression_service.compress,
            conv_id,
            supabase,
            api_key=api_key,
            model_string=model_string,
        )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/{conversation_id}/messages",
    status_code=status.HTTP_200_OK,
    summary="Send a message and receive a streaming SSE response",
)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    background_tasks: BackgroundTasks,
    token: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Primary generation endpoint.

    Steps:
      1. Validate conversation ownership and soft-delete status.
      2. Resolve model (request → user default) and fetch BYOK key.
      3. Persist user message.
      4. Return StreamingResponse (SSE) that assembles context and streams LLM output.
      5. On stream end: persist assistant message, trigger background jobs.

    SSE auth: JWT accepted via Authorization header OR ?token= query param
    (EventSource limitation — see MEMORY.md 2026-03-21).
    """
    if not body.content or not body.content.strip():
        raise ValidationError("Message content cannot be empty")

    supabase = get_supabase_client()
    user_id = current_user.user_id
    conv_id = str(conversation_id)

    # 1. Validate conversation
    conv = await _fetch_conversation(supabase, conv_id, user_id)

    # 2. Resolve model
    model_id_str: Optional[str] = (
        str(body.model_id) if body.model_id else None
    )
    if not model_id_str:
        model_id_str = await _fetch_user_default_model_id(supabase, user_id)
    if not model_id_str:
        raise ValidationError("No model selected and no default model configured")

    model_row = await _fetch_model_row(supabase, model_id_str)

    # 3. Fetch BYOK key for provider
    provider = model_row["provider"]
    api_key = await _fetch_byok_key(supabase, user_id, provider)
    if not api_key:
        raise PaymentRequiredError(
            f"No API key found for provider '{provider}'. "
            "Add one in Profile → API Keys."
        )

    # 4. Persist user message
    next_seq = await _get_next_sequence(supabase, conv_id)
    await _insert_message(supabase, conv_id, "user", body.content.strip(), next_seq)

    # 5. Return streaming SSE response
    return StreamingResponse(
        _stream_response(
            supabase=supabase,
            conv_id=conv_id,
            current_content=body.content.strip(),
            model_row=model_row,
            api_key=api_key,
            user_msg_sequence=next_seq,
            active_agent_id=conv.get("active_agent_id"),
            background_tasks=background_tasks,
            user_id=user_id,
            conv_title=conv.get("title"),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
