"""
Context stack assembly service — KIN-275 (L1-4+8) + KIN-290 (L5-7+9).

Entry point: assemble(conversation_id, user_id, query, model_context_window, supabase)
Returns: ContextStack dataclass

Layer ordering (ADR-003):
  [L1][L2][L3][L4][L5][L6][L7]
  [conversation history]
  [L8][L9]
  [current user message]  ← NOT assembled here; injected by the generation endpoint

Truncation priority when over budget (ADR-003 §3):
  L9 → L7 → L6 → L5 → L4 → history (oldest first) → L8 → L3 → L2 → L1

Schema ref: docs/db-schema-spec.md
ADR ref:    docs/adr-003-context-stack-generation.md, docs/adr-004-conversation-compression.md
"""
from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ContextStack:
    """All assembled layers for a single generation request."""

    l1_user_bio: str = ""
    l2_company: str = ""
    l3_project_instructions: str = ""
    l4_project_active_memory: str = ""   # TODO Sprint 5 — stub
    l5_agent_system_prompt: str = ""     # TODO Sprint 4 — filled by KIN-290
    l6_agent_active_memory: str = ""     # TODO Sprint 5 — stub
    l7_framework: str = ""               # TODO Sprint 4 — filled by KIN-290
    l8_project_rag: str = ""
    l9_agent_rag: str = ""               # TODO Sprint 4 — filled by KIN-290
    history: list[dict] = field(default_factory=list)
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# Main assembler
# ---------------------------------------------------------------------------


async def assemble(
    *,
    conversation_id: str,
    user_id: str,
    query: str,
    model_context_window: int,
    supabase: Any,
) -> ContextStack:
    """Assemble the full context stack for a generation request.

    Sprint 3: L1, L2, L3, L8 are active. L4-L7, L9 are stubs.
    Sprint 4: L5, L7, L9 filled in. (KIN-290)
    Sprint 5: L4, L6 filled in.
    """
    loop = asyncio.get_running_loop()

    async def db(fn):
        return await loop.run_in_executor(None, fn)

    # -------------------------------------------------------------------------
    # Fetch conversation to determine scope (project vs. company)
    # -------------------------------------------------------------------------
    conv_result = await db(
        lambda: supabase.table("conversations")
        .select("project_id, company_id, active_agent_id")
        .eq("id", conversation_id)
        .maybe_single()
        .execute()
    )
    if not conv_result.data:
        logger.error("Conversation %s not found during context assembly", conversation_id)
        return ContextStack()

    conv = conv_result.data
    project_id: Optional[str] = conv.get("project_id")
    company_id: str = conv["company_id"]
    active_agent_id: Optional[str] = conv.get("active_agent_id")

    # -------------------------------------------------------------------------
    # L1 — User bio
    # -------------------------------------------------------------------------
    l1 = await _fetch_l1(db, supabase, user_id)

    # -------------------------------------------------------------------------
    # L2 — Active company description
    # -------------------------------------------------------------------------
    l2 = await _fetch_l2(db, supabase, company_id)

    # -------------------------------------------------------------------------
    # L3 — Project instructions (project conversations only)
    # -------------------------------------------------------------------------
    l3 = ""
    if project_id:
        l3 = await _fetch_l3(db, supabase, project_id)

    # -------------------------------------------------------------------------
    # L4 — Project active memory (stub: Sprint 5)
    # -------------------------------------------------------------------------
    l4 = ""  # TODO Sprint 5: fetch active_memory_entries WHERE project_id = ?

    # -------------------------------------------------------------------------
    # L5 — Agent system prompt (stub Sprint 3, active Sprint 4 via KIN-290)
    # -------------------------------------------------------------------------
    l5 = ""  # TODO Sprint 4: filled by KIN-290 (active_agent_id)

    # -------------------------------------------------------------------------
    # L6 — Agent active memory (stub: Sprint 5)
    # -------------------------------------------------------------------------
    l6 = ""  # TODO Sprint 5: fetch active_memory_entries WHERE agent_instance_id = ?

    # -------------------------------------------------------------------------
    # L7 — Matched framework (stub Sprint 3, active Sprint 4 via KIN-290)
    # -------------------------------------------------------------------------
    l7 = ""  # TODO Sprint 4: filled by KIN-290 via framework_selection pipeline

    # -------------------------------------------------------------------------
    # Conversation history (ADR-003 §4 + ADR-004)
    # -------------------------------------------------------------------------
    history = await _fetch_history(db, supabase, conversation_id)

    # -------------------------------------------------------------------------
    # L8 — Project KB RAG (active when project has KB)
    # -------------------------------------------------------------------------
    l8 = ""
    if project_id:
        try:
            from app.services.rag_service import retrieve_for_project

            l8 = await retrieve_for_project(
                query=query,
                project_id=project_id,
                model_context_window=model_context_window,
                supabase=supabase,
            )
        except Exception:
            logger.exception("L8 RAG failed for project %s", project_id)

    # -------------------------------------------------------------------------
    # L9 — Agent KB RAG (stub Sprint 3, active Sprint 4 via KIN-290)
    # -------------------------------------------------------------------------
    l9 = ""  # TODO Sprint 4: filled by KIN-290

    # -------------------------------------------------------------------------
    # Build ContextStack and enforce token budget
    # -------------------------------------------------------------------------
    stack = ContextStack(
        l1_user_bio=l1,
        l2_company=l2,
        l3_project_instructions=l3,
        l4_project_active_memory=l4,
        l5_agent_system_prompt=l5,
        l6_agent_active_memory=l6,
        l7_framework=l7,
        l8_project_rag=l8,
        l9_agent_rag=l9,
        history=history,
    )
    stack = _enforce_budget(stack, model_context_window)
    stack.total_tokens = _count_stack_tokens(stack)
    return stack


# ---------------------------------------------------------------------------
# Sprint 4 extension — KIN-290: Agent layers (L5, L7, L9)
# Call assemble_with_agent_layers() to get the full 9-layer stack.
# -------------------------------------------------------------------------


async def assemble_with_agent_layers(
    *,
    conversation_id: str,
    user_id: str,
    query: str,
    model_context_window: int,
    supabase: Any,
) -> ContextStack:
    """Full 9-layer assembly — used from Sprint 4 onwards.

    Extends assemble() by filling in L5 (agent system prompt),
    L7 (framework pipeline output), and L9 (agent KB RAG).
    L6 remains a stub until Sprint 5.
    """
    # Start with the base Sprint-3 assembly
    stack = await assemble(
        conversation_id=conversation_id,
        user_id=user_id,
        query=query,
        model_context_window=model_context_window,
        supabase=supabase,
    )

    # Determine active agent
    loop = asyncio.get_running_loop()

    async def db(fn):
        return await loop.run_in_executor(None, fn)

    conv_result = await db(
        lambda: supabase.table("conversations")
        .select("project_id, active_agent_id")
        .eq("id", conversation_id)
        .maybe_single()
        .execute()
    )
    if not conv_result.data:
        return stack

    active_agent_id: Optional[str] = conv_result.data.get("active_agent_id")
    if not active_agent_id:
        # No agent active — return base Sprint-3 stack unchanged
        return stack

    # -------------------------------------------------------------------------
    # L5 — Agent system prompt
    # -------------------------------------------------------------------------
    agent_result = await db(
        lambda: supabase.table("agent_definitions")
        .select("instructions, category")
        .eq("id", active_agent_id)
        .maybe_single()
        .execute()
    )
    agent_data = agent_result.data if agent_result.data else {}
    instructions = agent_data.get("instructions") or ""
    agent_category: Optional[str] = agent_data.get("category")

    if instructions.strip():
        stack.l5_agent_system_prompt = f"[Agent Instructions]\n{instructions}"

    # -------------------------------------------------------------------------
    # L6 — Agent active memory (stub Sprint 4, active Sprint 5)
    # -------------------------------------------------------------------------
    stack.l6_agent_active_memory = ""  # TODO Sprint 5

    # -------------------------------------------------------------------------
    # L7 — Framework selection pipeline (KIN-289)
    # -------------------------------------------------------------------------
    try:
        from app.services.framework_selection import select_framework

        framework = await select_framework(
            query=query,
            agent_definition_id=active_agent_id,
            agent_category=agent_category,
            supabase=supabase,
        )
        if framework:
            stack.l7_framework = _format_framework(framework)
    except Exception:
        logger.exception(
            "Framework selection failed for agent %s — L7 empty", active_agent_id
        )
        stack.l7_framework = ""

    # -------------------------------------------------------------------------
    # L9 — Agent KB RAG
    # -------------------------------------------------------------------------
    project_id: Optional[str] = conv_result.data.get("project_id")
    try:
        from app.services.rag_service import retrieve_for_agent

        stack.l9_agent_rag = await retrieve_for_agent(
            query=query,
            agent_definition_id=active_agent_id,
            model_context_window=model_context_window,
            supabase=supabase,
        )
    except Exception:
        logger.exception(
            "L9 RAG failed for agent %s", active_agent_id
        )
        stack.l9_agent_rag = ""

    # Re-enforce budget with agent layers now populated
    stack = _enforce_budget(stack, model_context_window)
    stack.total_tokens = _count_stack_tokens(stack)
    return stack


def _format_framework(framework: dict) -> str:
    """Format a framework dict for injection as L7."""
    parts = [f"[Framework: {framework.get('name', 'Framework')}]"]

    if framework.get("description"):
        parts.append(framework["description"])

    if framework.get("when_to_apply"):
        parts.append("When to apply:")
        for trigger in framework["when_to_apply"]:
            parts.append(f"  - {trigger}")

    if framework.get("principles"):
        parts.append("Principles:")
        for p in framework["principles"]:
            parts.append(f"  - {p}")

    if framework.get("steps"):
        parts.append("Steps:")
        for i, s in enumerate(framework["steps"], 1):
            parts.append(f"  {i}. {s}")

    if framework.get("example_application"):
        parts.append(f"Example: {framework['example_application']}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Layer fetchers
# ---------------------------------------------------------------------------


async def _fetch_l1(db, supabase: Any, user_id: str) -> str:
    result = await db(
        lambda: supabase.table("users")
        .select("bio")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    bio = (result.data or {}).get("bio") or ""
    if not bio.strip():
        return ""
    return f"[User Profile]\n{bio}"


async def _fetch_l2(db, supabase: Any, company_id: str) -> str:
    result = await db(
        lambda: supabase.table("companies")
        .select("name, description")
        .eq("id", company_id)
        .maybe_single()
        .execute()
    )
    data = result.data or {}
    name = data.get("name") or ""
    description = data.get("description") or ""
    if not name:
        return ""
    parts = [f"[Company: {name}]"]
    if description.strip():
        parts.append(description)
    return "\n".join(parts)


async def _fetch_l3(db, supabase: Any, project_id: str) -> str:
    result = await db(
        lambda: supabase.table("projects")
        .select("name, instructions")
        .eq("id", project_id)
        .maybe_single()
        .execute()
    )
    data = result.data or {}
    instructions = data.get("instructions") or ""
    if not instructions.strip():
        return ""
    name = data.get("name") or "Project"
    return f"[Project Instructions — {name}]\n{instructions}"


async def _fetch_history(db, supabase: Any, conversation_id: str) -> list[dict]:
    """Fetch conversation history per ADR-003 §4 + ADR-004.

    If a conversation_summary exists: inject most-recent summary + verbatim window.
    Otherwise: all messages up to compression threshold.
    """
    from app.config import get_settings

    settings = get_settings()

    # Check for most-recent summary (ADR-004)
    summary_result = await db(
        lambda: supabase.table("conversation_summaries")
        .select("summary_text, messages_covered_up_to")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    messages_result = await db(
        lambda: supabase.table("messages")
        .select("role, content, sequence")
        .eq("conversation_id", conversation_id)
        .in_("role", ["user", "assistant"])
        .order("sequence", desc=False)
        .execute()
    )
    all_messages: list[dict] = messages_result.data or []

    if not summary_result.data:
        # No summary — return all messages (truncation handled by budget enforcement)
        return [{"role": m["role"], "content": m["content"]} for m in all_messages]

    # Summary exists — inject it + verbatim window (ADR-004 §2)
    summary = summary_result.data[0]
    covered_up_to: int = summary.get("messages_covered_up_to", 0)

    verbatim = [
        m for m in all_messages if m["sequence"] > covered_up_to
    ][-settings.VERBATIM_WINDOW:]

    history: list[dict] = [
        {
            "role": "system",
            "content": f"[Summary of earlier conversation]\n{summary['summary_text']}",
        }
    ]
    history.extend({"role": m["role"], "content": m["content"]} for m in verbatim)
    return history


# ---------------------------------------------------------------------------
# Token budget enforcement (ADR-003 §2, §3)
# ---------------------------------------------------------------------------


def _count_tokens(text: str) -> int:
    """Rough token estimate: ceil(chars / 4). No tiktoken dependency at runtime."""
    return math.ceil(len(text) / 4)


def _count_stack_tokens(stack: ContextStack) -> int:
    total = 0
    for text in [
        stack.l1_user_bio,
        stack.l2_company,
        stack.l3_project_instructions,
        stack.l4_project_active_memory,
        stack.l5_agent_system_prompt,
        stack.l6_agent_active_memory,
        stack.l7_framework,
        stack.l8_project_rag,
        stack.l9_agent_rag,
    ]:
        total += _count_tokens(text)
    for msg in stack.history:
        total += _count_tokens(msg.get("content", ""))
    return total


def _enforce_budget(stack: ContextStack, context_window: int) -> ContextStack:
    """Truncate layers in ADR-003 priority order until within budget."""
    budget = int(context_window * 0.80)
    total = _count_stack_tokens(stack)

    if total <= budget:
        return stack

    # ADR-003 truncation order (cut first → cut last):
    # 1. L9, 2. L7, 3. L6, 4. L5, 5. L4, 6. history (oldest first), 7. L8, 8. L3, 9. L2, 10. L1

    # Step 1-5: zero out stubs + agent layers
    for attr in ("l9_agent_rag", "l7_framework", "l6_agent_active_memory",
                 "l5_agent_system_prompt", "l4_project_active_memory"):
        if _count_stack_tokens(stack) <= budget:
            return stack
        setattr(stack, attr, "")

    # Step 6: trim history (oldest first, preserve most-recent)
    while stack.history and _count_stack_tokens(stack) > budget:
        stack.history.pop(0)

    # Step 7: reduce L8 (truncate text to first N chars)
    if _count_stack_tokens(stack) > budget:
        over = _count_stack_tokens(stack) - budget
        trim_chars = over * 4  # rough reverse of ceil(chars/4)
        if len(stack.l8_project_rag) > trim_chars:
            stack.l8_project_rag = stack.l8_project_rag[: len(stack.l8_project_rag) - trim_chars]
        else:
            stack.l8_project_rag = ""

    # Steps 8-10: truncate deterministic layers at hard caps
    _truncate_layer(stack, "l3_project_instructions", 500 * 4)  # 500 tokens ≈ 2000 chars
    _truncate_layer(stack, "l2_company", 300 * 4)
    _truncate_layer(stack, "l1_user_bio", 200 * 4)

    return stack


def _truncate_layer(stack: ContextStack, attr: str, max_chars: int) -> None:
    text = getattr(stack, attr)
    if len(text) > max_chars:
        setattr(stack, attr, text[:max_chars] + "…")
