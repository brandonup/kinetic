"""
Context assembler service — layers 1-9 + conversation history.

Assembles the 9-layer context stack for the chat generation endpoint.
Layers 1-6 are deterministic DB fetches; L7 is framework selection;
L8-L9 are RAG retrieval; conversation history completes the stack.

Spec: PRD §10 (Context Stack & Generation Engine)
Schema: db-schema-spec.md §1 (users), §3 (companies), §4 (projects),
        §5 (conversations), §8 (agent_definitions), §9 (agent_instances),
        §16 (active_memory_entries), §6 (messages), §7 (conversation_summaries)
Ticket: KIN-385
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

# Lazy imports to avoid triggering config.py / pydantic-settings at import time.
# These are imported inside methods that use them.

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level accessor — defined here so tests can patch it
# ---------------------------------------------------------------------------


def get_supabase_client():
    """Return the service-role Supabase client. Defined at module level so tests can patch it."""
    from app.db.supabase_client import get_supabase

    return get_supabase()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class AssembledContext:
    """Container for the assembled context stack.

    Attributes:
        system_parts: L1-L7 assembled text blocks (L7 added in Task 2).
        rag_chunks: L8+L9 RetrievedChunk objects (added in Task 3).
        rag_context_text: L8+L9 chunk texts joined (added in Task 3).
        model_context_window: From llm_models row.
        conversation_history: Recent messages (added in Task 4).
        rag_debug_contexts: Per-scope debug contexts for trace writes.
    """

    system_parts: list[str] = field(default_factory=list)
    rag_chunks: list = field(default_factory=list)
    rag_context_text: str = ""
    model_context_window: int = 100_000
    conversation_history: list[dict] = field(default_factory=list)
    rag_debug_contexts: list[tuple] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------


class ContextAssembler:
    """Assembles the multi-layer context stack from Supabase reads.

    All Supabase calls are wrapped in run_in_executor since the
    Supabase Python client is synchronous.
    """

    async def assemble(
        self,
        supabase,
        user_id: str,
        conversation_id: str,
        query_text: str,
        model_context_window: int = 100_000,
    ) -> AssembledContext:
        """Assemble layers 1-9 of the context stack plus conversation history.

        Args:
            supabase: Supabase service-role client.
            user_id: Authenticated user's UUID.
            conversation_id: Target conversation UUID.
            query_text: The user's current message (needed for L7/L8/L9).
            model_context_window: Context window size for RAG budget calculation.

        Returns:
            AssembledContext with system_parts, rag_chunks, rag_context_text,
            and conversation_history populated.

        Raises:
            ValueError: If conversation not found.
        """
        loop = asyncio.get_running_loop()
        ctx = AssembledContext(model_context_window=model_context_window)

        # Fetch conversation row to determine scope
        conv_res = await loop.run_in_executor(
            None,
            lambda: supabase.table("conversations")
            .select("company_id, project_id, active_agent_id")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
            .single()
            .execute(),
        )
        if not conv_res.data:
            raise ValueError(f"Conversation {conversation_id} not found for user {user_id}")

        company_id: str = conv_res.data["company_id"]
        project_id: str | None = conv_res.data.get("project_id")
        active_agent_id: str | None = conv_res.data.get("active_agent_id")

        # L1: User profile (always)
        await self._assemble_user_profile(loop, supabase, user_id, ctx)

        # L2: Company context (always)
        await self._assemble_company(loop, supabase, company_id, ctx)

        # L3: Project instructions (if project_id)
        if project_id:
            await self._assemble_project_instructions(loop, supabase, project_id, ctx)

        # L4: Project memory (if project_id)
        if project_id:
            await self._assemble_project_memory(loop, supabase, project_id, user_id, ctx)

        # L5: Agent definition instructions (if active_agent_id)
        if active_agent_id:
            await self._assemble_agent_instructions(loop, supabase, active_agent_id, ctx)

        # L6: Agent instance memory (if active_agent_id)
        if active_agent_id:
            await self._assemble_agent_memory(
                loop, supabase, active_agent_id, user_id, ctx
            )

        # Fetch OpenAI key once for L7 + L8/L9 (fail-open if missing)
        from app.services.user_keys import fetch_user_key_async

        openai_key: str | None = None
        if active_agent_id or project_id:
            openai_key = await fetch_user_key_async(supabase, user_id, "openai")
            if not openai_key:
                logger.info(
                    "No OpenAI BYOK key for user %s — skipping L7/L8/L9", user_id
                )

        # L7 + L8/L9: Run in parallel (both need OpenAI key, both fail-open)
        if active_agent_id and openai_key:
            framework_task = self._assemble_framework(
                supabase, active_agent_id, user_id, query_text, openai_key, ctx
            )
        else:
            framework_task = asyncio.sleep(0)  # no-op

        if openai_key:
            rag_task = self._assemble_rag(
                supabase, query_text, project_id, active_agent_id,
                openai_key, model_context_window, ctx,
            )
        else:
            rag_task = asyncio.sleep(0)  # no-op

        await asyncio.gather(framework_task, rag_task)

        # Conversation history (messages + optional summary)
        await self._assemble_conversation_history(loop, supabase, conversation_id, ctx)

        return ctx

    # ------------------------------------------------------------------
    # Layer helpers
    # ------------------------------------------------------------------

    async def _assemble_user_profile(
        self,
        loop: asyncio.AbstractEventLoop,
        supabase,
        user_id: str,
        ctx: AssembledContext,
    ) -> None:
        """L1: Fetch user profile and add to system_parts."""
        user_res = await loop.run_in_executor(
            None,
            lambda: supabase.table("users")
            .select("name, email, bio")
            .eq("id", user_id)
            .single()
            .execute(),
        )
        if not user_res.data:
            logger.warning("L1: user %s not found, skipping", user_id)
            return

        parts = [f"[User Profile]\nName: {user_res.data['name']}"]
        if user_res.data.get("email"):
            parts.append(f"Email: {user_res.data['email']}")
        if user_res.data.get("bio"):
            parts.append(f"Bio: {user_res.data['bio']}")
        ctx.system_parts.append("\n".join(parts))

    async def _assemble_company(
        self,
        loop: asyncio.AbstractEventLoop,
        supabase,
        company_id: str,
        ctx: AssembledContext,
    ) -> None:
        """L2: Fetch company info and add to system_parts."""
        comp_res = await loop.run_in_executor(
            None,
            lambda: supabase.table("companies")
            .select("name, description")
            .eq("id", company_id)
            .single()
            .execute(),
        )
        if not comp_res.data:
            logger.warning("L2: company %s not found, skipping", company_id)
            return

        block = f"[Company: {comp_res.data['name']}]"
        if comp_res.data.get("description"):
            block += f"\n{comp_res.data['description']}"
        ctx.system_parts.append(block)

    async def _assemble_project_instructions(
        self,
        loop: asyncio.AbstractEventLoop,
        supabase,
        project_id: str,
        ctx: AssembledContext,
    ) -> None:
        """L3: Fetch project instructions and add to system_parts."""
        proj_res = await loop.run_in_executor(
            None,
            lambda: supabase.table("projects")
            .select("instructions")
            .eq("id", project_id)
            .single()
            .execute(),
        )
        if not proj_res.data:
            logger.warning("L3: project %s not found, skipping", project_id)
            return

        instructions = proj_res.data.get("instructions")
        if instructions:
            ctx.system_parts.append(f"[Project Instructions]\n{instructions}")

    async def _assemble_project_memory(
        self,
        loop: asyncio.AbstractEventLoop,
        supabase,
        project_id: str,
        user_id: str,
        ctx: AssembledContext,
    ) -> None:
        """L4: Fetch project active memory entries and add to system_parts."""
        mem_res = await loop.run_in_executor(
            None,
            lambda: supabase.table("active_memory_entries")
            .select("content")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute(),
        )
        entries = mem_res.data or []
        if entries:
            contents = [e["content"] for e in entries]
            ctx.system_parts.append("[Project Memory]\n" + "\n".join(contents))

    async def _assemble_agent_instructions(
        self,
        loop: asyncio.AbstractEventLoop,
        supabase,
        agent_definition_id: str,
        ctx: AssembledContext,
    ) -> None:
        """L5: Fetch agent definition instructions and add to system_parts."""
        agent_res = await loop.run_in_executor(
            None,
            lambda: supabase.table("agent_definitions")
            .select("name, instructions")
            .eq("id", agent_definition_id)
            .single()
            .execute(),
        )
        if not agent_res.data:
            logger.warning("L5: agent_definition %s not found, skipping", agent_definition_id)
            return

        name = agent_res.data["name"]
        instructions = agent_res.data.get("instructions")
        if instructions:
            ctx.system_parts.append(f"[Agent: {name}]\n{instructions}")

    async def _assemble_agent_memory(
        self,
        loop: asyncio.AbstractEventLoop,
        supabase,
        agent_definition_id: str,
        user_id: str,
        ctx: AssembledContext,
    ) -> None:
        """L6: Look up or auto-create agent_instance, then fetch memory entries."""
        # Look up existing agent_instance
        instance_res = await loop.run_in_executor(
            None,
            lambda: supabase.table("agent_instances")
            .select("id")
            .eq("user_id", user_id)
            .eq("agent_definition_id", agent_definition_id)
            .maybe_single()
            .execute(),
        )

        if instance_res.data:
            instance_id = instance_res.data["id"]
        else:
            # Auto-create per ADR-003
            logger.info(
                "L6: auto-creating agent_instance for user %s, agent_def %s",
                user_id,
                agent_definition_id,
            )
            insert_res = await loop.run_in_executor(
                None,
                lambda: supabase.table("agent_instances")
                .insert({"user_id": user_id, "agent_definition_id": agent_definition_id})
                .execute(),
            )
            if not insert_res.data:
                logger.error(
                    "L6: failed to auto-create agent_instance for user %s, agent_def %s",
                    user_id,
                    agent_definition_id,
                )
                return
            instance_id = insert_res.data[0]["id"]

        # Fetch memory entries for this instance
        mem_res = await loop.run_in_executor(
            None,
            lambda: supabase.table("active_memory_entries")
            .select("content")
            .eq("agent_instance_id", instance_id)
            .eq("user_id", user_id)
            .execute(),
        )
        entries = mem_res.data or []
        if entries:
            contents = [e["content"] for e in entries]
            ctx.system_parts.append("[Agent Memory]\n" + "\n".join(contents))

    async def _assemble_framework(
        self,
        supabase,
        active_agent_id: str,
        user_id: str,
        query_text: str,
        openai_key: str,
        ctx: AssembledContext,
    ) -> None:
        """L7: Select a framework for the active agent and append to system_parts.

        Checks framework_overrides on the user's AgentInstance first:
          - disabled=True → skip L7 entirely
          - pinned list → force-inject pinned frameworks, skip pipeline
          - excluded list → filter excluded from candidate pool before selection

        Spec: docs/specs/agents.md §11.4
        Ticket: KIN-391
        """
        from app.services.rag.framework_selection import (
            fetch_pinned_frameworks,
            select_framework,
        )

        try:
            loop = asyncio.get_running_loop()

            # Fetch agent instance to check framework_overrides
            instance_res = await loop.run_in_executor(
                None,
                lambda: supabase.table("agent_instances")
                .select("framework_overrides")
                .eq("agent_definition_id", active_agent_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute(),
            )
            overrides = (instance_res.data or {}).get("framework_overrides", {})

            # Disabled: skip L7 entirely
            if overrides.get("disabled"):
                logger.info(
                    "L7 skipped: framework overrides disabled for agent %s, user %s",
                    active_agent_id, user_id,
                )
                return

            # Pinned: force-inject pinned frameworks, skip pipeline
            pinned = overrides.get("pinned", [])
            if pinned:
                matches = await fetch_pinned_frameworks(pinned, supabase)
                for match in matches:
                    if match.framework_text:
                        ctx.system_parts.append(
                            f"[Framework: {match.matched_framework_name}]\n{match.framework_text}"
                        )
                return

            # Normal pipeline with exclusions
            excluded = set(overrides.get("excluded", []))
            match = await select_framework(
                query_text, active_agent_id, supabase,
                openai_key=openai_key,
                excluded_ids=excluded if excluded else None,
            )
            if match.framework_text:
                if match.high_confidence:
                    ctx.system_parts.append(
                        f"[Framework: {match.matched_framework_name}]\n{match.framework_text}"
                    )
                else:
                    ctx.system_parts.append(
                        f"[Framework: {match.matched_framework_name} (moderate confidence match)]\n"
                        "This framework was matched with moderate confidence. Apply it only if it\n"
                        "directly addresses the user's question. If it seems tangential, ignore it\n"
                        f"and reason without a framework.\n\n{match.framework_text}"
                    )
        except Exception as exc:
            logger.warning("L7 framework selection failed — skipping: %s", exc)

    async def _assemble_rag(
        self,
        supabase,
        query_text: str,
        project_id: str | None,
        active_agent_id: str | None,
        openai_key: str,
        model_context_window: int,
        ctx: AssembledContext,
    ) -> None:
        """L8 (Project KB) + L9 (Agent KB): RAG retrieval via retrieve()."""
        from app.services.rag.debug_context import RetrievalDebugContext
        from app.services.rag.retrieval import RetrievalScope, retrieve

        all_chunks = []

        # L8: Project KB
        if project_id:
            debug_ctx = RetrievalDebugContext(scope="project_kb")
            try:
                chunks = await retrieve(
                    query_text,
                    scope=RetrievalScope.PROJECT_KB,
                    scope_id=UUID(project_id),
                    supabase=supabase,
                    openai_key=openai_key,
                    model_context_window=model_context_window,
                    debug_ctx=debug_ctx,
                )
                all_chunks.extend(chunks)
            except Exception as exc:
                logger.warning("L8 project KB retrieval failed — skipping: %s", exc)
                debug_ctx.gating_decision = "error"
                debug_ctx.error_message = str(exc)
            ctx.rag_debug_contexts.append(("project_kb", debug_ctx))

        # L9: Agent KB
        if active_agent_id:
            debug_ctx = RetrievalDebugContext(scope="agent_kb")
            try:
                chunks = await retrieve(
                    query_text,
                    scope=RetrievalScope.AGENT_KB,
                    scope_id=UUID(active_agent_id),
                    supabase=supabase,
                    openai_key=openai_key,
                    model_context_window=model_context_window,
                    debug_ctx=debug_ctx,
                )
                all_chunks.extend(chunks)
            except Exception as exc:
                logger.warning("L9 agent KB retrieval failed — skipping: %s", exc)
                debug_ctx.gating_decision = "error"
                debug_ctx.error_message = str(exc)
            ctx.rag_debug_contexts.append(("agent_kb", debug_ctx))

        ctx.rag_chunks.extend(all_chunks)

        if all_chunks:
            parts = []
            for chunk in all_chunks:
                parts.append(f"[Source: {chunk.document_title}]\n{chunk.text}")
            ctx.rag_context_text = "\n\n".join(parts)

    async def _assemble_conversation_history(
        self,
        loop: asyncio.AbstractEventLoop,
        supabase,
        conversation_id: str,
        ctx: AssembledContext,
    ) -> None:
        """Fetch recent messages and optional rolling summary for conversation history."""
        # Fetch messages ordered by sequence
        try:
            msg_res = await loop.run_in_executor(
                None,
                lambda: supabase.table("messages")
                .select("role, content, sequence")
                .eq("conversation_id", conversation_id)
                .order("sequence")
                .execute(),
            )
            messages = msg_res.data or []
        except Exception as exc:
            logger.warning("Failed to fetch messages for conversation %s: %s", conversation_id, exc)
            return

        # Fetch latest conversation summary
        summary_text: str | None = None
        try:
            sum_res = await loop.run_in_executor(
                None,
                lambda: supabase.table("conversation_summaries")
                .select("summary_text, messages_covered_up_to")
                .eq("conversation_id", conversation_id)
                .order("messages_covered_up_to", desc=True)
                .limit(1)
                .execute(),
            )
            if sum_res.data:
                summary_text = sum_res.data[0].get("summary_text")
        except Exception as exc:
            logger.warning("Failed to fetch conversation summary for %s: %s", conversation_id, exc)

        history: list[dict] = []

        # Filter to user/assistant messages only
        valid_messages = [
            m for m in messages if m.get("role") in ("user", "assistant")
        ]

        if sum_res.data and summary_text:
            # Summary available: prepend it, then show only messages not yet covered.
            # This prevents duplication between the summary and the recent window.
            messages_covered_up_to: int = sum_res.data[0]["messages_covered_up_to"]
            history.append({
                "role": "system",
                "content": f"[Previous conversation summary]\n{summary_text}",
            })
            recent = [m for m in valid_messages if m["sequence"] > messages_covered_up_to]
        else:
            # No summary: show the last 20 messages in full
            recent = valid_messages[-20:]

        for msg in recent:
            history.append({"role": msg["role"], "content": msg["content"]})

        ctx.conversation_history = history
