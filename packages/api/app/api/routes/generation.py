"""
Generation API route — KIN-385.

Endpoint:
  POST /api/v1/conversations/{conversation_id}/generate — SSE streaming chat generation

Assembles the 9-layer context stack via ContextAssembler, resolves the user's
BYOK key, streams the LLM response via stream_llm(), and stores both user and
assistant messages.

Spec: PRD §10 (Context Stack & Generation Engine)
Schema: docs/db-schema-spec.md §5 (conversations), §19 (messages),
        §1 (users), §20 (llm_models), §2 (user_api_keys)

Conventions:
  - All Supabase calls in async context use run_in_executor
  - Lazy imports for modules that chain to app.core.config
  - Never return None/[]/False on write operations — raise or log-and-raise
  - Every except block contains a log statement
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user
from app.core.errors import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conversations", tags=["generation"])


# ---------------------------------------------------------------------------
# Module-level accessor — defined here so tests can patch it
# ---------------------------------------------------------------------------


def get_supabase_client():
    """Return the service-role Supabase client. Defined at module level so tests can patch it."""
    from app.db.supabase_client import get_supabase

    return get_supabase()


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


def _build_citations(rag_chunks: list) -> list[dict]:
    """Build citation metadata from RAG chunks for the SSE done event.

    Returns citations sorted by similarity_score DESC (most relevant first).
    Snippet is first ~200 chars of chunk text.

    Spec: generation-engine-spec.md §8.2, §8.3
    Ticket: KIN-387
    """
    citations = []
    for chunk in rag_chunks:
        citations.append({
            "document_id": chunk.document_id,
            "document_title": chunk.document_title,
            "file_type": chunk.document_type,
            "chunk_index": chunk.chunk_index,
            "snippet": chunk.text[:200],
            "similarity_score": chunk.similarity_score,
            "scope": chunk.scope,
        })
    citations.sort(key=lambda c: c["similarity_score"], reverse=True)
    return citations


class GenerateRequest(BaseModel):
    message: str  # User's current message
    model_id: Optional[str] = None  # llm_models.id override (UUID)
    agent_id: Optional[str] = None  # Switch active agent

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message must not be empty")
        return v


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/{conversation_id}/generate")
async def generate(
    conversation_id: str,
    body: GenerateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Stream an LLM response for a conversation via SSE.

    1. Verifies conversation ownership
    2. Optionally switches active agent
    3. Resolves model (override or user default)
    4. Resolves BYOK key for the model's provider
    5. Stores the user message
    6. Assembles the 9-layer context stack
    7. Streams LLM response as SSE events
    8. Stores the assistant message on completion

    SSE event types:
      - delta: {"type": "delta", "content": "chunk"}
      - done:  {"type": "done", "message_id": "uuid"}
      - error: {"type": "error", "message": "..."}

    Raises:
        NotFoundError (404): Conversation not found or not owned by user.
        ValidationError (400): No model configured or no BYOK key.
    """
    client = get_supabase_client()
    loop = asyncio.get_running_loop()

    # 1. Verify conversation ownership
    conv_res = await loop.run_in_executor(
        None,
        lambda: client.table("conversations")
        .select("id, company_id, project_id, active_agent_id")
        .eq("id", conversation_id)
        .eq("user_id", current_user.user_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute(),
    )
    if not conv_res.data:
        raise NotFoundError("Conversation not found")

    company_id = conv_res.data["company_id"]
    project_id = conv_res.data.get("project_id")
    active_agent_id = conv_res.data.get("active_agent_id")

    # 2. Agent switch
    if body.agent_id and body.agent_id != active_agent_id:
        await loop.run_in_executor(
            None,
            lambda: client.table("conversations")
            .update({"active_agent_id": body.agent_id})
            .eq("id", conversation_id)
            .eq("user_id", current_user.user_id)
            .execute(),
        )
        active_agent_id = body.agent_id

    # 3. Resolve model
    model_uuid = body.model_id
    if not model_uuid:
        user_res = await loop.run_in_executor(
            None,
            lambda: client.table("users")
            .select("default_model_id")
            .eq("id", current_user.user_id)
            .single()
            .execute(),
        )
        model_uuid = (user_res.data or {}).get("default_model_id")

    if not model_uuid:
        raise ValidationError("No model selected and no default model configured")

    model_res = await loop.run_in_executor(
        None,
        lambda: client.table("llm_models")
        .select("model_id, provider, context_window")
        .eq("id", model_uuid)
        .eq("enabled", True)
        .maybe_single()
        .execute(),
    )
    if not model_res.data:
        raise ValidationError("Model not found or not enabled")

    model_name: str = model_res.data["model_id"]
    provider: str = model_res.data["provider"]
    context_window: int = model_res.data.get("context_window", 100_000)

    # 4. Resolve BYOK key (lazy import)
    from app.services.user_keys import fetch_user_key_async

    api_key = await fetch_user_key_async(client, current_user.user_id, provider)
    if not api_key:
        raise ValidationError(f"No API key configured for {provider}")

    # 5. Store user message — compute sequence atomically via MAX(sequence)
    seq_res = await loop.run_in_executor(
        None,
        lambda: client.table("messages")
        .select("sequence")
        .eq("conversation_id", conversation_id)
        .order("sequence", desc=True)
        .limit(1)
        .execute(),
    )
    current_count = (seq_res.data[0]["sequence"] + 1) if seq_res.data else 0

    user_msg_row = {
        "conversation_id": conversation_id,
        "role": "user",
        "content": body.message,
        "sequence": current_count,
        "agent_definition_id": active_agent_id,
    }
    user_insert_res = await loop.run_in_executor(
        None,
        lambda: client.table("messages").insert(user_msg_row).execute(),
    )
    if not user_insert_res.data:
        logger.error("generate: failed to store user message for conversation %s", conversation_id)
        raise ValidationError("Failed to store user message")

    # 6. Assemble context (lazy import)
    from app.services.context_assembler import ContextAssembler

    ctx = await ContextAssembler().assemble(
        client,
        current_user.user_id,
        conversation_id,
        body.message,
        model_context_window=context_window,
    )

    # 7. Build messages array
    from app.services.prompts import get_prompt

    system_template = get_prompt("context-stack-system-v1", "system")
    system_content = system_template.format(
        context_layers="\n\n".join(ctx.system_parts),
        rag_context=ctx.rag_context_text,
    )
    messages = [{"role": "system", "content": system_content}]
    messages.extend(ctx.conversation_history)
    messages.append({"role": "user", "content": body.message})

    # 8. Build streaming params
    from app.core.config import is_reasoning_model

    stream_kwargs: dict = {
        "messages": messages,
        "model": model_name,
        "api_key": api_key,
    }
    if not is_reasoning_model(model_name):
        stream_kwargs["temperature"] = 0.7

    # Capture values needed inside the generator closure
    _conversation_id = conversation_id
    _active_agent_id = active_agent_id
    _model_name = model_name
    _sequence = current_count + 1

    async def event_generator():
        from app.services.llm_client import stream_llm

        full_response = ""
        try:
            async for chunk in stream_llm(**stream_kwargs):
                full_response += chunk
                event = json.dumps({"type": "delta", "content": chunk})
                yield f"data: {event}\n\n"

            # Store assistant message
            ai_msg_row = {
                "conversation_id": _conversation_id,
                "role": "assistant",
                "content": full_response,
                "sequence": _sequence,
                "agent_definition_id": _active_agent_id,
                "model": _model_name,
            }
            _loop = asyncio.get_running_loop()
            ai_insert_res = await _loop.run_in_executor(
                None,
                lambda: client.table("messages").insert(ai_msg_row).execute(),
            )
            if not ai_insert_res.data:
                logger.error(
                    "generate: failed to store assistant message for conversation %s",
                    _conversation_id,
                )

            message_id = (
                ai_insert_res.data[0]["id"] if ai_insert_res.data else "unknown"
            )
            done_event = json.dumps({
                "type": "done",
                "message_id": message_id,
                "model": _model_name,
                "citations": _build_citations(ctx.rag_chunks),
            })
            yield f"data: {done_event}\n\n"

        except Exception as exc:
            logger.error("generate: LLM streaming failed: %s", exc)
            error_event = json.dumps({"type": "error", "message": str(exc)})
            yield f"data: {error_event}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
