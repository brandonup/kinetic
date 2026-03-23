"""
Context stack assembly service — KIN-275, KIN-290.

Assembles the 9-layer prompt context for a conversation.

Sprint 3 activates Layers 1–3 + 8 (L8 is a stub pending KIN-258).
Sprint 4 activates L5 (agent system prompt), L7 (framework), L9 (agent KB RAG).
L4 (project active memory) and L6 (agent active memory) remain stubs for Sprint 5.

Layer map:
  L1  — User bio            (users.bio)
  L2  — Company description (companies.description)
  L3  — Project instructions (projects.instructions, null for company convs)
  L4  — Project Active Memory    [STUB Sprint 5]
  L5  — Agent system prompt      [ACTIVE Sprint 4, when agent active]
  L6  — Agent Active Memory      [STUB Sprint 5]
  L7  — Matched framework        [ACTIVE Sprint 4, when agent active + framework selected]
  L8  — Project KB RAG           [STUB KIN-258]
  L9  — Agent KB RAG             [ACTIVE Sprint 4, when agent active + agent has KB]

Conversation history sits between assembled layers and the current user message.
If a conversation_summaries row exists, inject summary + N verbatim recent messages.
If no summary, inject all messages up to compression threshold.

Spec ref: docs/prd.md §10 (Context Stack)
          docs/specs/kin-257-projects-conversations-spec.md §2.5
Schema ref: docs/db-schema-spec.md
ADR ref: docs/adr-003-agents-architecture.md, docs/adr-005-agents-framework-selection.md
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services import framework_selection as fw_selection_service
from app.services import rag as rag_service

# Number of verbatim messages to keep when a summary exists.
# ADR-004 (Gilfoyle) will confirm this value — using sensible default.
VERBATIM_WINDOW = 6


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


@dataclass
class ContextStack:
    """
    Assembled context for a single LLM request.

    system_prompt — concatenation of all active layers (L1-L9).
    history       — recent conversation messages formatted for LiteLLM:
                    [{"role": "user"|"assistant", "content": "..."}]
    """

    system_prompt: str
    history: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Async helper (sync supabase client via executor)
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


# ---------------------------------------------------------------------------
# Layer fetchers
# ---------------------------------------------------------------------------


async def _fetch_conversation(supabase: Any, conversation_id: str) -> dict:
    result = await _run(
        lambda: supabase.table("conversations")
        .select("id, company_id, project_id, active_agent_id, user_id, title")
        .eq("id", conversation_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    return result.data or {}


async def _fetch_user_bio(supabase: Any, user_id: str) -> str:
    result = await _run(
        lambda: supabase.table("users")
        .select("bio")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if result.data:
        return result.data.get("bio") or ""
    return ""


async def _fetch_company_description(supabase: Any, company_id: str) -> str:
    result = await _run(
        lambda: supabase.table("companies")
        .select("description")
        .eq("id", company_id)
        .maybe_single()
        .execute()
    )
    if result.data:
        return result.data.get("description") or ""
    return ""


async def _fetch_project_instructions(
    supabase: Any, project_id: str
) -> str:
    result = await _run(
        lambda: supabase.table("projects")
        .select("instructions")
        .eq("id", project_id)
        .maybe_single()
        .execute()
    )
    if result.data:
        return result.data.get("instructions") or ""
    return ""


async def _fetch_agent_definition(supabase: Any, agent_definition_id: str) -> dict:
    """Fetch the AgentDefinition row for L5 (system prompt) and knowledge_base_id."""
    result = await _run(
        lambda: supabase.table("agent_definitions")
        .select("id, instructions, knowledge_base_id")
        .eq("id", agent_definition_id)
        .maybe_single()
        .execute()
    )
    return result.data or {}


async def _fetch_agent_instance(
    supabase: Any, agent_definition_id: str, user_id: str
) -> dict:
    """Fetch the AgentInstance for framework overrides (Step 2 of framework pipeline)."""
    result = await _run(
        lambda: supabase.table("agent_instances")
        .select("framework_overrides")
        .eq("agent_definition_id", agent_definition_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if result.data:
        return result.data
    return {"framework_overrides": {"pinned": [], "excluded": []}}


async def _fetch_knowledge_base_id(
    supabase: Any, *, project_id: Optional[str] = None, agent_definition_id: Optional[str] = None
) -> Optional[str]:
    """Look up the knowledge_base id for a project or agent definition."""
    query = supabase.table("knowledge_bases").select("id")
    if project_id:
        query = query.eq("project_id", project_id)
    elif agent_definition_id:
        query = query.eq("agent_definition_id", agent_definition_id)
    else:
        return None
    result = await _run(lambda: query.maybe_single().execute())
    if result.data:
        return result.data.get("id")
    return None


async def _fetch_messages(supabase: Any, conversation_id: str) -> list[dict]:
    """Fetch all non-system messages ordered by sequence."""
    result = await _run(
        lambda: supabase.table("messages")
        .select("role, content, sequence")
        .eq("conversation_id", conversation_id)
        .neq("role", "system")
        .order("sequence", desc=False)
        .execute()
    )
    return result.data or []


async def _fetch_latest_summary(
    supabase: Any, conversation_id: str
) -> Optional[dict]:
    """Return the most recent conversation_summaries row, or None."""
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


# ---------------------------------------------------------------------------
# History assembly
# ---------------------------------------------------------------------------


def _build_history(
    messages: list[dict],
    summary: Optional[dict],
) -> list[dict[str, str]]:
    """
    Build the conversation history to inject into the prompt.

    If a summary exists:
      - Inject a synthetic 'user' message containing the summary.
      - Follow with the last VERBATIM_WINDOW messages.
    If no summary:
      - Inject all messages.
    """
    history: list[dict[str, str]] = []

    if summary:
        covered_up_to = summary["messages_covered_up_to"]
        verbatim = [m for m in messages if m["sequence"] > covered_up_to][-VERBATIM_WINDOW:]
        history.append({
            "role": "user",
            "content": f"[Conversation summary]\n{summary['summary_text']}",
        })
        history.append({"role": "assistant", "content": "[Summary acknowledged]"})
        history.extend({"role": m["role"], "content": m["content"]} for m in verbatim)
    else:
        history.extend({"role": m["role"], "content": m["content"]} for m in messages)

    return history


# ---------------------------------------------------------------------------
# Layer assembly helpers
# ---------------------------------------------------------------------------


def _section(header: str, content: str) -> str:
    """Format a named section for the system prompt. Returns '' if content empty."""
    if not content or not content.strip():
        return ""
    return f"== {header} ==\n{content.strip()}\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def assemble(
    conversation_id: str,
    user_id: str,
    supabase: Any,
    *,
    query: str = "",
) -> ContextStack:
    """
    Assemble the full 9-layer context stack for a conversation.

    Parameters
    ----------
    conversation_id : str
        UUID of the conversation being responded to.
    user_id : str
        Authenticated user making the request.
    supabase : Any
        Supabase client (sync, wrapped via asyncio executor).
    query : str
        The current user message text, used for RAG retrieval (L8, L9).
        Pass empty string when assembling without a query (e.g., tests).

    Returns
    -------
    ContextStack
        system_prompt — all layers concatenated (empty stubs excluded).
        history       — formatted conversation history.
    """
    # Fetch conversation metadata
    conv = await _fetch_conversation(supabase, conversation_id)
    company_id: str = conv.get("company_id", "")
    project_id: Optional[str] = conv.get("project_id")
    active_agent_id: Optional[str] = conv.get("active_agent_id")

    # Fetch all layers concurrently where possible
    bio_task = asyncio.create_task(_fetch_user_bio(supabase, user_id))
    company_task = asyncio.create_task(_fetch_company_description(supabase, company_id))
    project_task = (
        asyncio.create_task(_fetch_project_instructions(supabase, project_id))
        if project_id
        else None
    )
    messages_task = asyncio.create_task(_fetch_messages(supabase, conversation_id))
    summary_task = asyncio.create_task(_fetch_latest_summary(supabase, conversation_id))

    # Resolve project KB ID for RAG (only if project conversation)
    kb_id_task = (
        asyncio.create_task(_fetch_knowledge_base_id(supabase, project_id=project_id))
        if project_id
        else None
    )

    # Agent layer tasks (L5, L7, L9) — only when an agent is active
    agent_def_task = (
        asyncio.create_task(_fetch_agent_definition(supabase, active_agent_id))
        if active_agent_id
        else None
    )
    agent_instance_task = (
        asyncio.create_task(_fetch_agent_instance(supabase, active_agent_id, user_id))
        if active_agent_id
        else None
    )

    # Await all
    l1_bio = await bio_task
    l2_company = await company_task
    l3_project = await project_task if project_task else ""
    messages = await messages_task
    summary = await summary_task
    kb_id = await kb_id_task if kb_id_task else None

    # L8 — Project KB RAG (stub: KIN-258 fills in the actual retrieval)
    rag_chunks: list[rag_service.RetrievedChunk] = []
    if kb_id and query:
        rag_chunks = await rag_service.retrieve(kb_id, query, supabase)
    l8_rag = rag_service.format_chunks_for_prompt(rag_chunks)

    # ---------------------------------------------------------------------------
    # Agent layers (L5, L7, L9) — activated when active_agent_id is set
    # ---------------------------------------------------------------------------

    l5_agent_instructions = ""
    l7_framework = ""
    l9_agent_rag = ""

    if active_agent_id and agent_def_task and agent_instance_task:
        agent_def = await agent_def_task
        agent_instance = await agent_instance_task

        # L5 — Agent system prompt
        l5_agent_instructions = agent_def.get("instructions") or ""

        # L7 — Framework selection pipeline
        # Build enriched query (last 2 user messages + current) per ADR-005 §1
        recent_user_msgs = [m["content"] for m in messages if m["role"] == "user"][-2:]
        enriched_query = "\n\n".join(recent_user_msgs + ([query] if query else []))

        framework_overrides = agent_instance.get("framework_overrides") or {}
        selected_framework = await fw_selection_service.select_framework(
            supabase,
            active_agent_id,
            enriched_query,
            framework_overrides,
        )
        if selected_framework:
            l7_framework = fw_selection_service.format_framework_for_prompt(selected_framework)

        # L9 — Agent KB RAG
        agent_kb_id = agent_def.get("knowledge_base_id")
        if agent_kb_id and query:
            agent_rag_chunks = await rag_service.retrieve(agent_kb_id, query, supabase)
            l9_agent_rag = rag_service.format_chunks_for_prompt(agent_rag_chunks)

    # ---------------------------------------------------------------------------
    # Assemble system prompt from all layers
    # ---------------------------------------------------------------------------

    sections = [
        _section("User Profile", l1_bio),
        _section("Company Context", l2_company),
        _section("Project Context", l3_project),              # L3: active for project convs
        _section("Active Memory", ""),                         # L4: TODO Sprint 5
        _section("Agent Instructions", l5_agent_instructions), # L5: active when agent set
        _section("Agent Memory", ""),                          # L6: TODO Sprint 5
        _section("Framework", l7_framework),                   # L7: active when agent + fw selected
        _section("Knowledge Base", l8_rag),                    # L8: stub (KIN-258)
        _section("Agent Knowledge Base", l9_agent_rag),        # L9: active when agent has KB
    ]

    system_prompt = "\n".join(s for s in sections if s)

    # ---------------------------------------------------------------------------
    # Build conversation history
    # ---------------------------------------------------------------------------

    history = _build_history(messages, summary)

    return ContextStack(system_prompt=system_prompt, history=history)
