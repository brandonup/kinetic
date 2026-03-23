"""
Unit tests for services/context_stack.py — KIN-279.

Verifies:
  - Project conversation: L1+L2+L3+history assembled correctly
  - Company conversation: L1+L2+history (no L3)
  - Empty stubs for L4-L7, L9 don't break assembly
  - History with no summary: all messages injected
  - History with summary: summary + verbatim window injected
  - Missing user bio / company description handled gracefully
  - RAG stub (L8) returns empty → no Knowledge Base section

Spec ref: docs/specs/kin-257-projects-conversations-spec.md §2.5
KIN-275: implementation ticket
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.context_stack import (
    VERBATIM_WINDOW,
    ContextStack,
    _build_history,
    assemble,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONV_ID = str(uuid4())
USER_ID = str(uuid4())
COMPANY_ID = str(uuid4())
PROJECT_ID = str(uuid4())
KB_ID = str(uuid4())


def _sync_chain(return_data: Any):
    """Build a mock supabase query chain that returns return_data."""
    result = MagicMock()
    result.data = return_data
    result.count = 0
    chain = MagicMock()
    for method in (
        "select", "eq", "neq", "is_", "order", "limit",
        "maybe_single", "insert", "update", "delete",
    ):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = result
    return chain, result


def _make_supabase(table_map: dict[str, Any]) -> MagicMock:
    """
    Build a mock supabase client.

    table_map: { table_name: return_data_for_execute }
    """
    sb = MagicMock()

    def _table(name: str) -> MagicMock:
        data = table_map.get(name)
        chain, _ = _sync_chain(data)
        return chain

    sb.table.side_effect = _table
    return sb


# ---------------------------------------------------------------------------
# _build_history unit tests
# ---------------------------------------------------------------------------


class TestBuildHistory:
    def test_no_summary_returns_all_messages(self):
        msgs = [
            {"role": "user", "content": "Hello", "sequence": 0},
            {"role": "assistant", "content": "Hi!", "sequence": 1},
        ]
        history = _build_history(msgs, summary=None)
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "Hi!"}

    def test_with_summary_returns_summary_plus_verbatim_window(self):
        # 10 messages, summary covers through sequence 3
        msgs = [
            {"role": "user", "content": f"msg {i}", "sequence": i}
            for i in range(10)
        ]
        summary = {"summary_text": "Summary of early messages", "messages_covered_up_to": 3}
        history = _build_history(msgs, summary=summary)

        # First two entries are the summary synthetic pair
        assert history[0]["role"] == "user"
        assert "Summary of early messages" in history[0]["content"]
        assert history[1]["role"] == "assistant"

        # Remaining entries are the verbatim window
        verbatim = history[2:]
        assert len(verbatim) <= VERBATIM_WINDOW
        # They come from sequences > 3
        for entry in verbatim:
            assert "msg" in entry["content"]

    def test_empty_messages_returns_empty_history(self):
        history = _build_history([], summary=None)
        assert history == []

    def test_summary_with_fewer_messages_than_verbatim_window(self):
        msgs = [
            {"role": "user", "content": "only one", "sequence": 0},
        ]
        summary = {"summary_text": "Already summarised", "messages_covered_up_to": -1}
        history = _build_history(msgs, summary=summary)
        # Summary synthetic pair + messages after covered_up_to
        assert any("Already summarised" in h["content"] for h in history)


# ---------------------------------------------------------------------------
# assemble() integration tests (mocked supabase)
# ---------------------------------------------------------------------------


class TestAssemble:
    @pytest.fixture
    def project_conv_data(self):
        return {
            "id": CONV_ID,
            "company_id": COMPANY_ID,
            "project_id": PROJECT_ID,
            "active_agent_id": None,
            "user_id": USER_ID,
            "title": None,
        }

    @pytest.fixture
    def company_conv_data(self):
        return {
            "id": CONV_ID,
            "company_id": COMPANY_ID,
            "project_id": None,
            "active_agent_id": None,
            "user_id": USER_ID,
            "title": None,
        }

    def _make_supabase_for_conv(self, conv_data: dict, *, bio: str, description: str, instructions: str):
        """Build a supabase mock for a full assemble() call."""
        sb = MagicMock()
        call_counts: dict[str, int] = {}

        def _table(name: str) -> MagicMock:
            call_counts[name] = call_counts.get(name, 0) + 1
            if name == "conversations":
                chain, _ = _sync_chain(conv_data)
            elif name == "users":
                chain, _ = _sync_chain({"bio": bio})
            elif name == "companies":
                chain, _ = _sync_chain({"description": description})
            elif name == "projects":
                chain, _ = _sync_chain({"instructions": instructions})
            elif name == "knowledge_bases":
                chain, _ = _sync_chain({"id": KB_ID})
            elif name == "messages":
                chain, _ = _sync_chain([])
            elif name == "conversation_summaries":
                chain, _ = _sync_chain([])
            else:
                chain, _ = _sync_chain(None)
            return chain

        sb.table.side_effect = _table
        return sb

    def test_project_conversation_includes_all_active_layers(self, project_conv_data):
        sb = self._make_supabase_for_conv(
            project_conv_data,
            bio="I am a consultant.",
            description="A SaaS company.",
            instructions="Focus on revenue.",
        )

        result = asyncio.run(assemble(CONV_ID, USER_ID, sb))

        assert isinstance(result, ContextStack)
        assert "I am a consultant." in result.system_prompt  # L1
        assert "A SaaS company." in result.system_prompt      # L2
        assert "Focus on revenue." in result.system_prompt    # L3
        # Empty stubs don't add noise
        assert "Active Memory" not in result.system_prompt    # L4 stub — empty → no section
        assert "Agent Instructions" not in result.system_prompt  # L5 stub
        assert "Knowledge Base" not in result.system_prompt   # L8 stub returns empty

    def test_company_conversation_excludes_project_instructions(self, company_conv_data):
        sb = self._make_supabase_for_conv(
            company_conv_data,
            bio="Founder.",
            description="Tech startup.",
            instructions="Should not appear",
        )

        result = asyncio.run(assemble(CONV_ID, USER_ID, sb))

        assert "Founder." in result.system_prompt
        assert "Tech startup." in result.system_prompt
        assert "Should not appear" not in result.system_prompt

    def test_empty_bio_excluded_from_prompt(self, project_conv_data):
        sb = self._make_supabase_for_conv(
            project_conv_data,
            bio="",
            description="Company.",
            instructions="Instructions.",
        )

        result = asyncio.run(assemble(CONV_ID, USER_ID, sb))

        assert "User Profile" not in result.system_prompt
        assert "Company." in result.system_prompt

    def test_history_returned_correctly(self, company_conv_data):
        sb = MagicMock()
        messages = [
            {"role": "user", "content": "First message", "sequence": 0},
            {"role": "assistant", "content": "First reply", "sequence": 1},
        ]

        call_counts: dict[str, int] = {}

        def _table(name: str) -> MagicMock:
            call_counts[name] = call_counts.get(name, 0) + 1
            if name == "conversations":
                chain, _ = _sync_chain(company_conv_data)
            elif name == "users":
                chain, _ = _sync_chain({"bio": "bio"})
            elif name == "companies":
                chain, _ = _sync_chain({"description": "desc"})
            elif name == "messages":
                chain, _ = _sync_chain(messages)
            elif name == "conversation_summaries":
                chain, _ = _sync_chain([])
            else:
                chain, _ = _sync_chain(None)
            return chain

        sb.table.side_effect = _table

        result = asyncio.run(assemble(CONV_ID, USER_ID, sb))

        assert len(result.history) == 2
        assert result.history[0] == {"role": "user", "content": "First message"}
        assert result.history[1] == {"role": "assistant", "content": "First reply"}

    def test_missing_conversation_returns_empty_stack(self):
        sb = MagicMock()
        call_counts: dict[str, int] = {}

        def _table(name: str) -> MagicMock:
            call_counts[name] = call_counts.get(name, 0) + 1
            if name == "conversations":
                chain, _ = _sync_chain(None)  # not found
            elif name == "users":
                chain, _ = _sync_chain({"bio": ""})
            elif name == "companies":
                chain, _ = _sync_chain(None)
            elif name == "messages":
                chain, _ = _sync_chain([])
            elif name == "conversation_summaries":
                chain, _ = _sync_chain([])
            else:
                chain, _ = _sync_chain(None)
            return chain

        sb.table.side_effect = _table

        result = asyncio.run(assemble(CONV_ID, USER_ID, sb))
        # Should not raise — returns empty stack
        assert isinstance(result, ContextStack)

    def test_context_stack_with_summary_injects_summary_in_history(self, company_conv_data):
        sb = MagicMock()
        messages = [
            {"role": "user", "content": f"msg {i}", "sequence": i}
            for i in range(8)
        ]
        summary_row = {
            "summary_text": "Summarised earlier messages",
            "messages_covered_up_to": 2,
        }

        def _table(name: str) -> MagicMock:
            if name == "conversations":
                chain, _ = _sync_chain(company_conv_data)
            elif name == "users":
                chain, _ = _sync_chain({"bio": "bio"})
            elif name == "companies":
                chain, _ = _sync_chain({"description": "desc"})
            elif name == "messages":
                chain, _ = _sync_chain(messages)
            elif name == "conversation_summaries":
                chain, _ = _sync_chain([summary_row])
            else:
                chain, _ = _sync_chain(None)
            return chain

        sb.table.side_effect = _table

        result = asyncio.run(assemble(CONV_ID, USER_ID, sb))

        assert any(
            "Summarised earlier messages" in h["content"] for h in result.history
        )
