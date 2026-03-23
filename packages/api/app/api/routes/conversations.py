"""
Conversation CRUD + generation endpoint — KIN-272, KIN-276.

POST /api/v1/conversations/{id}/messages — KIN-276 (Big Head)
  Assembles context, streams SSE response, persists messages.

Schema ref: docs/db-schema-spec.md §5 (conversations), §6 (messages), §7 (summaries)
Spec ref:   docs/specs/kin-257-projects-conversations-spec.md §2.2, §2.3
ADR ref:    adr-003-context-stack-generation, adr-004-conversation-compression
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any, AsyncGenerator, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.core.errors import (
    ForbiddenError,
    LLMAuthError,
    LLMError,
    NotFoundError,
    PaymentRequiredError,
    ValidationError,
)
from app.db import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateConversationRequest(BaseModel):
    company_id: UUID
    project_id: Optional[UUID] = None
    title: Optional[str] = None


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    active_agent_id: Optional[UUID] = None


class SendMessageRequest(BaseModel):
    content: str
    model_id: Optional[UUID] = None  # FK to llm_models; None → use user default

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("content must not be empty")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


async def _get_conversation(
    supabase: Any, conversation_id: str, user_id: str
) -> dict:
    result = await _run(
        lambda: supabase.table("conversations")
        .select("*")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise NotFoundError("Conversation not found")
    return result.data


async def _next_sequence(supabase: Any, conversation_id: str) -> int:
    result = await _run(
        lambda: supabase.table("messages")
        .select("sequence")
        .eq("conversation_id", conversation_id)
        .order("sequence", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["sequence"] + 1
    return 0


async def _count_user_messages(supabase: Any, conversation_id: str) -> int:
    result = await _run(
        lambda: supabase.table("messages")
        .select("id")
        .eq("conversation_id", conversation_id)
        .eq("role", "user")
        .execute()
    )
    return len(result.data or [])


async def _resolve_byok_key(
    supabase: Any, user_id: str, provider: str
) -> str:
    """Fetch and decrypt the user's BYOK key for the given provider.
    Raises PaymentRequiredError if no key exists."""
    result = await _run(
        lambda: supabase.table("user_api_keys")
        .select("key_ciphertext, key_nonce")
        .eq("user_id", user_id)
        .eq("provider", provider)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise PaymentRequiredError(
            f"No API key configured for provider '{provider}'. "
            "Add your key in Profile → API Keys."
        )
    from app.services.encryption import decrypt_key

    return decrypt_key(
        result.data["key_ciphertext"], result.data["key_nonce"]
    )


def _provider_for_model(model_string: str) -> str:
    """Infer the LLM provider from the model identifier string."""
    if model_string.startswith("claude"):
        return "anthropic"
    if model_string.startswith("gpt") or model_string.startswith("o1") or model_string.startswith("o3"):
        return "openai"
    if model_string.startswith("gemini"):
        return "google"
    if model_string.startswith("llama") or model_string.startswith("mixtral"):
        return "groq"
    return "openai"  # sensible fallback


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: CreateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    company_id = str(body.company_id)
    project_id = str(body.project_id) if body.project_id else None

    # Verify company ownership
    comp = await _run(
        lambda: supabase.table("companies")
        .select("id")
        .eq("id", company_id)
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )
    if not comp.data:
        raise ForbiddenError("Company not found or does not belong to you")

    # Verify project ownership if provided
    if project_id:
        proj = await _run(
            lambda: supabase.table("projects")
            .select("id")
            .eq("id", project_id)
            .eq("user_id", current_user.id)
            .eq("company_id", company_id)
            .maybe_single()
            .execute()
        )
        if not proj.data:
            raise ForbiddenError("Project not found or does not belong to this company")

    row = {
        "user_id": current_user.id,
        "company_id": company_id,
        "project_id": project_id,
        "title": body.title,
        "active_agent_id": None,
    }
    result = await _run(
        lambda: supabase.table("conversations").insert(row).execute()
    )
    if not result.data:
        raise ValidationError("Failed to create conversation")
    return result.data[0]


@router.get("")
async def list_conversations(
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    query = (
        supabase.table("conversations")
        .select("id, company_id, project_id, title, active_agent_id, created_at, updated_at")
        .eq("user_id", current_user.id)
        .is_("deleted_at", "null")
    )
    if company_id:
        query = query.eq("company_id", company_id)
    if project_id:
        query = query.eq("project_id", project_id)
    query = query.order("updated_at", desc=True)

    result = await _run(lambda: query.execute())
    return {"conversations": result.data or []}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    conv = await _get_conversation(supabase, str(conversation_id), current_user.id)

    msg_result = await _run(
        lambda: supabase.table("messages")
        .select("id, role, content, agent_definition_id, model, sequence, created_at")
        .eq("conversation_id", str(conversation_id))
        .neq("role", "system")
        .order("sequence", desc=False)
        .execute()
    )
    conv["messages"] = msg_result.data or []
    return conv


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: UUID,
    body: UpdateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    supabase = get_supabase_client()
    conv_id = str(conversation_id)
    await _get_conversation(supabase, conv_id, current_user.id)

    updates: dict = {"updated_at": datetime.datetime.utcnow().isoformat()}
    if body.title is not None:
        updates["title"] = body.title

    if "active_agent_id" in body.model_fields_set:
        if body.active_agent_id is not None:
            agent_id = str(body.active_agent_id)
            agent = await _run(
                lambda: supabase.table("agent_definitions")
                .select("id, visibility, owner_id")
                .eq("id", agent_id)
                .maybe_single()
                .execute()
            )
            if not agent.data:
                raise NotFoundError("Agent not found")
            if (
                agent.data["visibility"] != "public"
                and agent.data["owner_id"] != current_user.id
            ):
                raise ForbiddenError("You do not have access to this agent")
            updates["active_agent_id"] = agent_id
        else:
            updates["active_agent_id"] = None

    result = await _run(
        lambda: supabase.table("conversations")
        .update(updates)
        .eq("id", conv_id)
        .eq("user_id", current_user.id)
        .execute()
    )
    if not result.data:
        raise NotFoundError("Conversation not found")
    return result.data[0]


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    supabase = get_supabase_client()
    conv_id = str(conversation_id)
    await _get_conversation(supabase, conv_id, current_user.id)
    await _run(
        lambda: supabase.table("conversations")
        .update({"deleted_at": datetime.datetime.utcnow().isoformat()})
        .eq("id", conv_id)
        .eq("user_id", current_user.id)
        .execute()
    )


# ---------------------------------------------------------------------------
# Generation endpoint — KIN-276
# ---------------------------------------------------------------------------


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    current_user: CurrentUser = Depends(get_current_user),
    token: Optional[str] = Query(default=None),  # SSE auth via query param
) -> StreamingResponse:
    """
    POST /api/v1/conversations/{id}/messages

    1. Validate + persist user message
    2. Resolve model + BYOK key
    3. Assemble context stack
    4. Stream LLM response via SSE
    5. Persist assistant message
    6. Dispatch background jobs (non-blocking)

    SSE event format:
      data: {"delta": "..."}\n\n   — each content chunk
      data: {"done": true}\n\n    — terminal event
      data: {"error": "..."}\n\n  — on failure
    """
    supabase = get_supabase_client()
    settings = get_settings()
    conv_id = str(conversation_id)

    # 1. Verify conversation
    conv = await _get_conversation(supabase, conv_id, current_user.id)

    # 2. Persist user message
    seq = await _next_sequence(supabase, conv_id)
    user_msg_row = {
        "conversation_id": conv_id,
        "role": "user",
        "content": body.content,
        "sequence": seq,
        "agent_definition_id": conv.get("active_agent_id"),
    }
    user_msg_result = await _run(
        lambda: supabase.table("messages").insert(user_msg_row).execute()
    )
    if not user_msg_result.data:
        raise ValidationError("Failed to persist user message")
    user_msg_id = user_msg_result.data[0]["id"]

    # 3. Resolve model
    model_id = str(body.model_id) if body.model_id else None
    if not model_id:
        # Fall back to user's default model
        profile = await _run(
            lambda: supabase.table("users")
            .select("default_model_id")
            .eq("id", current_user.id)
            .maybe_single()
            .execute()
        )
        if profile.data and profile.data.get("default_model_id"):
            model_id = profile.data["default_model_id"]

    if not model_id:
        raise PaymentRequiredError(
            "No model selected and no default model configured. "
            "Set a default model in Profile."
        )

    # Fetch model details
    model_row = await _run(
        lambda: supabase.table("llm_models")
        .select("model_id, provider, context_window, enabled")
        .eq("id", model_id)
        .maybe_single()
        .execute()
    )
    if not model_row.data:
        raise ValidationError("Selected model not found")
    if not model_row.data.get("enabled", False):
        raise ValidationError("Selected model is not enabled")

    model_string: str = model_row.data["model_id"]
    provider: str = model_row.data.get("provider") or _provider_for_model(model_string)
    context_window: int = model_row.data.get("context_window") or 128_000

    # Fetch BYOK key
    byok_key = await _resolve_byok_key(supabase, current_user.id, provider)

    # 4. Assemble context stack
    from app.services.context_stack import assemble

    context = await assemble(
        conversation_id=conv_id,
        user_id=current_user.id,
        query=body.content,
        model_context_window=context_window,
        supabase=supabase,
    )

    # Build LiteLLM messages array
    llm_messages = _build_llm_messages(context, body.content)

    # 5. Stream SSE
    async def event_stream() -> AsyncGenerator[str, None]:
        from app.services.llm_client import stream_completion

        full_response = ""
        try:
            async for delta in stream_completion(
                messages=llm_messages,
                model=model_string,
                api_key=byok_key,
                provider=provider,
            ):
                full_response += delta
                yield f"data: {json.dumps({'delta': delta})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except LLMAuthError as exc:
            logger.error("LLM auth failed for user %s: %s", current_user.id, exc)
            yield f"data: {json.dumps({'error': 'llm_auth_failed', 'message': str(exc.message)})}\n\n"
            return
        except LLMError as exc:
            logger.error("LLM error for user %s: %s", current_user.id, exc)
            yield f"data: {json.dumps({'error': 'llm_error', 'message': str(exc.message)})}\n\n"
            return
        except Exception as exc:
            logger.exception("Unexpected error in generation for user %s", current_user.id)
            yield f"data: {json.dumps({'error': 'internal_error', 'message': 'Generation failed'})}\n\n"
            return

        # 6. Persist assistant message (after stream complete)
        next_seq = seq + 1
        assistant_msg_row = {
            "conversation_id": conv_id,
            "role": "assistant",
            "content": full_response,
            "sequence": next_seq,
            "model": model_string,
            "agent_definition_id": conv.get("active_agent_id"),
        }
        try:
            await _run(
                lambda: supabase.table("messages").insert(assistant_msg_row).execute()
            )
            # Bump conversation updated_at
            await _run(
                lambda: supabase.table("conversations")
                .update({"updated_at": datetime.datetime.utcnow().isoformat()})
                .eq("id", conv_id)
                .execute()
            )
        except Exception:
            logger.exception("Failed to persist assistant message for conv %s", conv_id)
            yield f"data: {json.dumps({'error': 'persistence_failed', 'message': 'Response was generated but could not be saved. Please try again.'})}\n\n"
            return

        # 7. Background jobs (non-blocking) — ADR-004
        _dispatch_background_jobs(
            supabase=supabase,
            conv_id=conv_id,
            user_id=current_user.id,
            conv_title=conv.get("title"),
            model_string=model_string,
            provider=provider,
            byok_key=byok_key,
            seq=next_seq,
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _build_llm_messages(context: "ContextStack", user_message: str) -> list[dict]:  # type: ignore[name-defined]
    """Convert ContextStack layers to LiteLLM messages array (ADR-003 ordering)."""
    from app.services.context_stack import ContextStack

    messages: list[dict] = []

    # Build system prompt from deterministic layers L1–L7
    system_parts: list[str] = []
    for layer_text in [
        context.l1_user_bio,
        context.l2_company,
        context.l3_project_instructions,
        context.l4_project_active_memory,
        context.l5_agent_system_prompt,
        context.l6_agent_active_memory,
        context.l7_framework,
    ]:
        if layer_text and layer_text.strip():
            system_parts.append(layer_text)

    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    # Inject conversation history (user/assistant only) — ADR-003 §4
    for msg in context.history:
        if msg["role"] in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})

    # RAG layers L8 + L9 injected just before user message
    rag_parts: list[str] = []
    if context.l8_project_rag and context.l8_project_rag.strip():
        rag_parts.append(context.l8_project_rag)
    if context.l9_agent_rag and context.l9_agent_rag.strip():
        rag_parts.append(context.l9_agent_rag)
    if rag_parts:
        messages.append({
            "role": "system",
            "content": "\n\n".join(rag_parts),
        })

    # Current user message
    messages.append({"role": "user", "content": user_message})
    return messages


def _dispatch_background_jobs(
    *,
    supabase: Any,
    conv_id: str,
    user_id: str,
    conv_title: Optional[str],
    model_string: str,
    provider: str,
    byok_key: str,
    seq: int,
) -> None:
    """Fire-and-forget background jobs. Errors here must not affect the SSE stream."""
    import asyncio

    from app.services.task_dispatcher import TaskDispatcher

    dispatcher = TaskDispatcher()

    # Auto-title on first message (seq == 1 means first assistant message)
    if seq == 1 and not conv_title:
        dispatcher.dispatch(
            _generate_title_job,
            supabase=supabase,
            conv_id=conv_id,
            model_string=model_string,
            byok_key=byok_key,
        )

    # Compression check — ADR-004: fire when user message count > 20
    # We use seq as a proxy: every 2 seqs = 1 exchange, so check at even seqs
    # Actual count is fetched in the job
    dispatcher.dispatch(
        _check_compression_job,
        supabase=supabase,
        conv_id=conv_id,
        user_id=user_id,
        model_string=model_string,
        byok_key=byok_key,
    )


async def _generate_title_job(
    *,
    supabase: Any,
    conv_id: str,
    model_string: str,
    byok_key: str,
) -> None:
    """Generate a conversation title from the first message exchange."""
    try:
        result = await _run(
            lambda: supabase.table("messages")
            .select("role, content")
            .eq("conversation_id", conv_id)
            .in_("role", ["user", "assistant"])
            .order("sequence", desc=False)
            .limit(2)
            .execute()
        )
        if not result.data or len(result.data) < 2:
            return

        first_user = next((m for m in result.data if m["role"] == "user"), None)
        if not first_user:
            return

        prompt = (
            "Generate a short, descriptive title (5-8 words) for a conversation that starts with:\n"
            f'"{first_user["content"][:500]}"\n\n'
            "Respond with ONLY the title, no quotes, no punctuation at the end."
        )
        from app.services.llm_client import complete

        title = await complete(
            messages=[{"role": "user", "content": prompt}],
            model=model_string,
            api_key=byok_key,
            max_tokens=20,
        )
        if title:
            await _run(
                lambda: supabase.table("conversations")
                .update({"title": title.strip()[:100]})
                .eq("id", conv_id)
                .is_("title", "null")
                .execute()
            )
    except Exception:
        logger.exception("Title generation failed for conv %s", conv_id)


async def _check_compression_job(
    *,
    supabase: Any,
    conv_id: str,
    user_id: str,
    model_string: str,
    byok_key: str,
) -> None:
    """Trigger rolling summary if user message count exceeds ADR-004 threshold."""
    try:
        from app.config import get_settings

        settings = get_settings()
        count = await _count_user_messages(supabase, conv_id)
        if count > settings.COMPRESSION_THRESHOLD:
            from app.services.compression import compress_conversation

            await compress_conversation(
                supabase=supabase,
                conv_id=conv_id,
                user_id=user_id,
                model_string=model_string,
                byok_key=byok_key,
            )
    except Exception:
        logger.exception("Compression check failed for conv %s", conv_id)
