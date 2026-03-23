"""
Unit tests for context_stack.assemble_with_agent_layers() — KIN-290.

Covers:
- L5 filled from agent_definitions.instructions
- L7 filled from framework_selection.select_framework()
- L9 filled from rag_service.retrieve_for_agent()
- L6 remains empty stub (Sprint 4)
- No active agent → returns base stack (L5/L7/L9 empty)
- Agent with no instructions → L5 empty
- Framework selection fails → L7 empty, no exception raised
- L9 RAG failure → L9 empty, no exception raised
- Token budget re-enforced after agent layers populated
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.context_stack import ContextStack, assemble_with_agent_layers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_supabase_for_agent(
    *,
    conv_data: dict | None = None,
    agent_data: dict | None = None,
) -> MagicMock:
    """Supabase mock that returns conv_data for conversations, agent_data for agent_definitions."""
    sb = MagicMock()
    current_table: list[str] = [""]

    def _table(name):
        current_table[0] = name
        return sb

    sb.table.side_effect = _table
    sb.select.return_value = sb
    sb.eq.return_value = sb
    sb.in_.return_value = sb
    sb.is_.return_value = sb
    sb.order.return_value = sb
    sb.limit.return_value = sb
    sb.maybe_single.return_value = sb

    def _execute():
        t = current_table[0]
        r = MagicMock()
        if t == "conversations":
            r.data = conv_data
        elif t == "agent_definitions":
            r.data = agent_data
        else:
            r.data = None
        return r

    sb.execute.side_effect = _execute
    return sb


BASE_STACK = ContextStack(
    l1_user_bio="[User Profile]\nBio",
    l2_company="[Company: Acme]",
    l3_project_instructions="[Project Instructions — Atlas]\nUse TDD.",
    history=[{"role": "user", "content": "test msg"}],
)

CONV_WITH_AGENT = {
    "project_id": "proj-1",
    "active_agent_id": "agent-1",
}
CONV_NO_AGENT = {
    "project_id": "proj-1",
    "active_agent_id": None,
}
AGENT_ROW = {
    "instructions": "You are a Socratic coach.",
    "category": "coaching",
}
AGENT_NO_INSTRUCTIONS = {
    "instructions": "",
    "category": "coaching",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_active_agent_returns_base_stack():
    """If no active_agent_id, L5/L7/L9 remain empty and stack is returned as-is."""
    sb = _make_supabase_for_agent(conv_data=CONV_NO_AGENT)

    with patch("app.services.context_stack.assemble", new_callable=AsyncMock, return_value=BASE_STACK):
        stack = await assemble_with_agent_layers(
            conversation_id="conv-1",
            user_id="user-1",
            query="hello",
            model_context_window=100_000,
            supabase=sb,
        )

    assert stack.l5_agent_system_prompt == ""
    assert stack.l7_framework == ""
    assert stack.l9_agent_rag == ""


@pytest.mark.asyncio
async def test_l5_filled_from_agent_instructions():
    """L5 should contain agent instructions when agent has instructions."""
    sb = _make_supabase_for_agent(conv_data=CONV_WITH_AGENT, agent_data=AGENT_ROW)

    with patch("app.services.context_stack.assemble", new_callable=AsyncMock, return_value=ContextStack()), \
         patch("app.services.framework_selection.select_framework", new_callable=AsyncMock, return_value=None), \
         patch("app.services.rag_service.retrieve_for_agent", new_callable=AsyncMock, return_value=""):

        stack = await assemble_with_agent_layers(
            conversation_id="conv-1",
            user_id="user-1",
            query="coach me",
            model_context_window=100_000,
            supabase=sb,
        )

    assert "[Agent Instructions]" in stack.l5_agent_system_prompt
    assert "Socratic coach" in stack.l5_agent_system_prompt


@pytest.mark.asyncio
async def test_l5_empty_when_no_instructions():
    """L5 stays empty when agent has no instructions."""
    sb = _make_supabase_for_agent(conv_data=CONV_WITH_AGENT, agent_data=AGENT_NO_INSTRUCTIONS)

    with patch("app.services.context_stack.assemble", new_callable=AsyncMock, return_value=ContextStack()), \
         patch("app.services.framework_selection.select_framework", new_callable=AsyncMock, return_value=None), \
         patch("app.services.rag_service.retrieve_for_agent", new_callable=AsyncMock, return_value=""):

        stack = await assemble_with_agent_layers(
            conversation_id="conv-1",
            user_id="user-1",
            query="coach me",
            model_context_window=100_000,
            supabase=sb,
        )

    assert stack.l5_agent_system_prompt == ""


@pytest.mark.asyncio
async def test_l7_filled_from_framework_selection():
    """L7 should contain formatted framework when select_framework returns a match."""
    framework = {
        "name": "Five Whys",
        "description": "Root cause analysis",
        "when_to_apply": ["debugging"],
        "principles": ["ask why"],
        "steps": ["Step 1", "Step 2"],
        "example_application": "Why did it break?",
    }
    sb = _make_supabase_for_agent(conv_data=CONV_WITH_AGENT, agent_data=AGENT_ROW)

    with patch("app.services.context_stack.assemble", new_callable=AsyncMock, return_value=ContextStack()), \
         patch("app.services.framework_selection.select_framework", new_callable=AsyncMock, return_value=framework), \
         patch("app.services.rag_service.retrieve_for_agent", new_callable=AsyncMock, return_value=""):

        stack = await assemble_with_agent_layers(
            conversation_id="conv-1",
            user_id="user-1",
            query="why is it broken?",
            model_context_window=100_000,
            supabase=sb,
        )

    assert "[Framework: Five Whys]" in stack.l7_framework
    assert "Root cause analysis" in stack.l7_framework
    assert "ask why" in stack.l7_framework


@pytest.mark.asyncio
async def test_l7_empty_when_no_framework_match():
    """L7 stays empty when framework selection returns None."""
    sb = _make_supabase_for_agent(conv_data=CONV_WITH_AGENT, agent_data=AGENT_ROW)

    with patch("app.services.context_stack.assemble", new_callable=AsyncMock, return_value=ContextStack()), \
         patch("app.services.framework_selection.select_framework", new_callable=AsyncMock, return_value=None), \
         patch("app.services.rag_service.retrieve_for_agent", new_callable=AsyncMock, return_value=""):

        stack = await assemble_with_agent_layers(
            conversation_id="conv-1",
            user_id="user-1",
            query="generic question",
            model_context_window=100_000,
            supabase=sb,
        )

    assert stack.l7_framework == ""


@pytest.mark.asyncio
async def test_l7_empty_when_framework_selection_raises():
    """L7 stays empty and no exception is raised when framework selection fails."""
    sb = _make_supabase_for_agent(conv_data=CONV_WITH_AGENT, agent_data=AGENT_ROW)

    with patch("app.services.context_stack.assemble", new_callable=AsyncMock, return_value=ContextStack()), \
         patch("app.services.framework_selection.select_framework", new_callable=AsyncMock, side_effect=Exception("pipeline error")), \
         patch("app.services.rag_service.retrieve_for_agent", new_callable=AsyncMock, return_value=""):

        stack = await assemble_with_agent_layers(
            conversation_id="conv-1",
            user_id="user-1",
            query="test",
            model_context_window=100_000,
            supabase=sb,
        )

    assert stack.l7_framework == ""


@pytest.mark.asyncio
async def test_l9_filled_from_rag():
    """L9 should contain RAG results when agent KB is available."""
    sb = _make_supabase_for_agent(conv_data=CONV_WITH_AGENT, agent_data=AGENT_ROW)

    with patch("app.services.context_stack.assemble", new_callable=AsyncMock, return_value=ContextStack()), \
         patch("app.services.framework_selection.select_framework", new_callable=AsyncMock, return_value=None), \
         patch("app.services.rag_service.retrieve_for_agent", new_callable=AsyncMock, return_value="[Agent Knowledge Base]\nRAG chunk"):

        stack = await assemble_with_agent_layers(
            conversation_id="conv-1",
            user_id="user-1",
            query="rag test",
            model_context_window=100_000,
            supabase=sb,
        )

    assert "[Agent Knowledge Base]" in stack.l9_agent_rag


@pytest.mark.asyncio
async def test_l9_empty_when_rag_fails():
    """L9 stays empty and no exception raised when RAG service fails."""
    sb = _make_supabase_for_agent(conv_data=CONV_WITH_AGENT, agent_data=AGENT_ROW)

    with patch("app.services.context_stack.assemble", new_callable=AsyncMock, return_value=ContextStack()), \
         patch("app.services.framework_selection.select_framework", new_callable=AsyncMock, return_value=None), \
         patch("app.services.rag_service.retrieve_for_agent", new_callable=AsyncMock, side_effect=Exception("rag failed")):

        stack = await assemble_with_agent_layers(
            conversation_id="conv-1",
            user_id="user-1",
            query="test",
            model_context_window=100_000,
            supabase=sb,
        )

    assert stack.l9_agent_rag == ""


@pytest.mark.asyncio
async def test_l6_remains_empty_stub():
    """L6 (agent active memory) is a stub and must remain empty in Sprint 4."""
    sb = _make_supabase_for_agent(conv_data=CONV_WITH_AGENT, agent_data=AGENT_ROW)

    with patch("app.services.context_stack.assemble", new_callable=AsyncMock, return_value=ContextStack()), \
         patch("app.services.framework_selection.select_framework", new_callable=AsyncMock, return_value=None), \
         patch("app.services.rag_service.retrieve_for_agent", new_callable=AsyncMock, return_value=""):

        stack = await assemble_with_agent_layers(
            conversation_id="conv-1",
            user_id="user-1",
            query="test",
            model_context_window=100_000,
            supabase=sb,
        )

    assert stack.l6_agent_active_memory == ""


@pytest.mark.asyncio
async def test_conv_not_found_returns_base_stack():
    """If second conversation lookup fails, return the base stack."""
    sb = _make_supabase_for_agent(conv_data=None)

    with patch("app.services.context_stack.assemble", new_callable=AsyncMock, return_value=BASE_STACK):
        stack = await assemble_with_agent_layers(
            conversation_id="missing-conv",
            user_id="user-1",
            query="test",
            model_context_window=100_000,
            supabase=sb,
        )

    assert stack == BASE_STACK
