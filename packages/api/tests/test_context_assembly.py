"""
Tests for ContextAssembler service — layers 1-9 + conversation history.

Ticket: KIN-385
Covers: L1 (user profile), L2 (company), L3 (project instructions),
        L4 (project memory), L5 (agent instructions), L6 (agent memory + auto-create),
        L7 (framework selection), L8 (project KB RAG), L9 (agent KB RAG),
        conversation history (messages + rolling summary).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.context_assembler import AssembledContext, ContextAssembler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Fixed UUIDs for deterministic tests
USER_ID = str(uuid4())
CONVERSATION_ID = str(uuid4())
COMPANY_ID = str(uuid4())
PROJECT_ID = str(uuid4())
AGENT_DEF_ID = str(uuid4())
AGENT_INSTANCE_ID = str(uuid4())


def _mock_response(data):
    """Create a mock Supabase response with .data attribute."""
    resp = MagicMock()
    resp.data = data
    return resp


def _build_mock_supabase(table_responses: dict) -> MagicMock:
    """Build a mock Supabase client configured with per-table, per-call responses.

    Args:
        table_responses: Dict mapping table names to a list of responses.
            Each call to that table consumes the next response in the list.
            Each response entry is the raw data (will be wrapped in _mock_response).

    Returns:
        A MagicMock configured to behave like the Supabase client.
    """
    mock_client = MagicMock()
    # Track call counts per table to return correct response in sequence
    call_counters: dict[str, int] = {}

    def _table_factory(table_name: str):
        """Return a mock table object that chains .select/.eq/.is_/.single/.maybe_single/.insert/.execute."""
        if table_name not in call_counters:
            call_counters[table_name] = 0

        responses = table_responses.get(table_name, [])
        idx = min(call_counters[table_name], len(responses) - 1) if responses else 0
        call_counters[table_name] = call_counters.get(table_name, 0) + 1

        data = responses[idx] if responses else None

        chain = MagicMock()
        chain.select.return_value = chain
        chain.insert.return_value = chain
        chain.eq.return_value = chain
        chain.is_.return_value = chain
        chain.single.return_value = chain
        chain.maybe_single.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = _mock_response(data)
        return chain

    mock_client.table.side_effect = _table_factory
    return mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAssembleProjectConversationAllLayers:
    """Test that a project + agent conversation produces L1-L6."""

    @pytest.mark.asyncio
    async def test_assemble_project_conversation_all_layers(self):
        mock_sb = _build_mock_supabase({
            # Conversation fetch
            "conversations": [
                {"company_id": COMPANY_ID, "project_id": PROJECT_ID, "active_agent_id": AGENT_DEF_ID},
            ],
            # L1: user profile
            "users": [
                {"name": "Alice", "email": "alice@example.com", "bio": "Product designer"},
            ],
            # L2: company
            "companies": [
                {"name": "Acme Corp", "description": "A leading AI company"},
            ],
            # L3: project instructions
            "projects": [
                {"instructions": "Focus on user onboarding"},
            ],
            # L4 + L6: active_memory_entries (first call = project memory, second = agent memory)
            "active_memory_entries": [
                [{"content": "User prefers concise responses"}],
                [{"content": "Agent learned user likes bullet points"}],
            ],
            # L5: agent definition
            "agent_definitions": [
                {"name": "Strategist", "instructions": "You are a strategic advisor"},
            ],
            # L6: agent_instances lookup
            "agent_instances": [
                {"id": AGENT_INSTANCE_ID},
            ],
        })

        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="Hello",
        )

        assert isinstance(result, AssembledContext)
        parts = result.system_parts

        # All 6 layers present
        labels = [
            "[User Profile]",
            "[Company: Acme Corp]",
            "[Project Instructions]",
            "[Project Memory]",
            "[Agent: Strategist]",
            "[Agent Memory]",
        ]
        for label in labels:
            assert any(label in p for p in parts), f"Missing layer: {label}"


class TestAssembleCompanyConversation:
    """Test company-level conversation (no project, no agent) produces only L1 and L2."""

    @pytest.mark.asyncio
    async def test_assemble_company_conversation(self):
        mock_sb = _build_mock_supabase({
            "conversations": [
                {"company_id": COMPANY_ID, "project_id": None, "active_agent_id": None},
            ],
            "users": [
                {"name": "Bob", "email": "bob@example.com", "bio": "Engineer"},
            ],
            "companies": [
                {"name": "Widgets Inc", "description": "Making widgets"},
            ],
        })

        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="Hi",
        )

        parts = result.system_parts
        assert len(parts) == 2
        assert "[User Profile]" in parts[0]
        assert "[Company: Widgets Inc]" in parts[1]
        # No project or agent layers
        combined = "\n".join(parts)
        assert "[Project Instructions]" not in combined
        assert "[Project Memory]" not in combined
        assert "[Agent:" not in combined
        assert "[Agent Memory]" not in combined


class TestAssembleProjectNoAgent:
    """Test project conversation without agent produces L1-L4 only."""

    @pytest.mark.asyncio
    async def test_assemble_project_no_agent(self):
        mock_sb = _build_mock_supabase({
            "conversations": [
                {"company_id": COMPANY_ID, "project_id": PROJECT_ID, "active_agent_id": None},
            ],
            "users": [
                {"name": "Carol", "email": "carol@example.com", "bio": "Analyst"},
            ],
            "companies": [
                {"name": "DataCo", "description": None},
            ],
            "projects": [
                {"instructions": "Analyze quarterly reports"},
            ],
            "active_memory_entries": [
                [{"content": "Q1 was strong"}],
            ],
        })

        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="What's the status?",
        )

        parts = result.system_parts
        # L1, L2, L3, L4 present
        assert any("[User Profile]" in p for p in parts)
        assert any("[Company: DataCo]" in p for p in parts)
        assert any("[Project Instructions]" in p for p in parts)
        assert any("[Project Memory]" in p for p in parts)
        # No L5/L6
        combined = "\n".join(parts)
        assert "[Agent:" not in combined
        assert "[Agent Memory]" not in combined


class TestAssembleAgentNoProject:
    """Test agent conversation at company level (no project) produces L1, L2, L5, L6."""

    @pytest.mark.asyncio
    async def test_assemble_agent_no_project(self):
        mock_sb = _build_mock_supabase({
            "conversations": [
                {"company_id": COMPANY_ID, "project_id": None, "active_agent_id": AGENT_DEF_ID},
            ],
            "users": [
                {"name": "Dave", "email": "dave@example.com", "bio": "Manager"},
            ],
            "companies": [
                {"name": "TechStart", "description": "Early-stage startup"},
            ],
            "agent_definitions": [
                {"name": "Coach", "instructions": "You are a leadership coach"},
            ],
            "agent_instances": [
                {"id": AGENT_INSTANCE_ID},
            ],
            "active_memory_entries": [
                [{"content": "User is working on team culture"}],
            ],
        })

        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="How should I handle this?",
        )

        parts = result.system_parts
        # L1, L2, L5, L6 present
        assert any("[User Profile]" in p for p in parts)
        assert any("[Company: TechStart]" in p for p in parts)
        assert any("[Agent: Coach]" in p for p in parts)
        assert any("[Agent Memory]" in p for p in parts)
        # No L3/L4
        combined = "\n".join(parts)
        assert "[Project Instructions]" not in combined
        assert "[Project Memory]" not in combined


class TestMissingBioGraceful:
    """Test that a null bio does not crash and L1 is still assembled."""

    @pytest.mark.asyncio
    async def test_missing_bio_graceful(self):
        mock_sb = _build_mock_supabase({
            "conversations": [
                {"company_id": COMPANY_ID, "project_id": None, "active_agent_id": None},
            ],
            "users": [
                {"name": "Eve", "email": "eve@example.com", "bio": None},
            ],
            "companies": [
                {"name": "NullBioCo", "description": "Testing null bio"},
            ],
        })

        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="Test",
        )

        parts = result.system_parts
        assert len(parts) == 2
        user_part = parts[0]
        assert "[User Profile]" in user_part
        assert "Name: Eve" in user_part
        assert "Bio:" not in user_part


class TestAgentInstanceAutoCreated:
    """Test that when no agent_instance exists, one is auto-created and L6 is assembled."""

    @pytest.mark.asyncio
    async def test_agent_instance_auto_created(self):
        new_instance_id = str(uuid4())

        mock_sb = _build_mock_supabase({
            "conversations": [
                {"company_id": COMPANY_ID, "project_id": None, "active_agent_id": AGENT_DEF_ID},
            ],
            "users": [
                {"name": "Frank", "email": "frank@example.com", "bio": "Developer"},
            ],
            "companies": [
                {"name": "NewAgentCo", "description": "Testing auto-create"},
            ],
            "agent_definitions": [
                {"name": "Advisor", "instructions": "You give advice"},
            ],
            # First call: maybe_single returns None (no instance), second call: insert returns new row
            "agent_instances": [
                None,
                [{"id": new_instance_id}],
            ],
            "active_memory_entries": [
                [{"content": "First memory for new instance"}],
            ],
        })

        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="Hello advisor",
        )

        parts = result.system_parts
        # L5 and L6 should be present
        assert any("[Agent: Advisor]" in p for p in parts)
        assert any("[Agent Memory]" in p for p in parts)

        # Verify insert was called (the second call to agent_instances table)
        table_calls = [
            call.args[0]
            for call in mock_sb.table.call_args_list
        ]
        assert table_calls.count("agent_instances") == 2  # lookup + insert


# ---------------------------------------------------------------------------
# Helper: base mock supabase for L7/L8/L9/history tests (L1-L6 minimal)
# ---------------------------------------------------------------------------


def _base_mock_sb_with_agent(framework_overrides=None):
    """Return a mock supabase pre-configured for a conversation with an agent + project.

    Args:
        framework_overrides: Dict for the agent_instances override lookup (KIN-391).
            Defaults to empty overrides (no pin/exclude/disable).
    """
    if framework_overrides is None:
        framework_overrides = {"pinned": [], "excluded": [], "disabled": False}
    return _build_mock_supabase({
        "conversations": [
            {"company_id": COMPANY_ID, "project_id": PROJECT_ID, "active_agent_id": AGENT_DEF_ID},
        ],
        "users": [{"name": "Tester", "email": "tester@example.com", "bio": "QA"}],
        "companies": [{"name": "TestCo", "description": "Testing"}],
        "projects": [{"instructions": "Test instructions"}],
        "active_memory_entries": [
            [{"content": "project memory"}],
            [{"content": "agent memory"}],
        ],
        "agent_definitions": [{"name": "TestAgent", "instructions": "Be helpful"}],
        # Two calls: (1) L6 agent memory instance lookup, (2) L7 overrides lookup
        "agent_instances": [
            {"id": AGENT_INSTANCE_ID},
            {"framework_overrides": framework_overrides},
        ],
        "messages": [[]],
        "conversation_summaries": [[]],
    })


# ---------------------------------------------------------------------------
# L7 Tests — Framework Selection
# ---------------------------------------------------------------------------


class TestL7FrameworkMatched:
    """L7: Framework match found — framework_text appears in system_parts."""

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    async def test_l7_framework_matched(self, mock_select):
        from app.services.rag.framework_selection import FrameworkMatch

        mock_select.return_value = FrameworkMatch(
            matched_framework_id="fw-1",
            matched_framework_name="SWOT Analysis",
            framework_text="Framework: SWOT Analysis\n\nDescription: Strategic analysis tool",
        )

        mock_sb = _base_mock_sb_with_agent()
        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="How should I approach this?",
        )

        assert any("[Framework: SWOT Analysis]" in p for p in result.system_parts)
        mock_select.assert_called_once()


class TestL7NoMatch:
    """L7: No framework match — system_parts unchanged by L7."""

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_l7_no_match(self, mock_retrieve, mock_select):
        from app.services.rag.framework_selection import FrameworkMatch

        mock_select.return_value = FrameworkMatch(
            matched_framework_id=None,
            matched_framework_name=None,
            framework_text=None,
        )
        mock_retrieve.return_value = []

        mock_sb = _base_mock_sb_with_agent()
        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="Just a question",
        )

        combined = "\n".join(result.system_parts)
        assert "[Framework:" not in combined


# ---------------------------------------------------------------------------
# L8/L9 Tests — RAG Retrieval
# ---------------------------------------------------------------------------


def _make_mock_chunk(doc_title: str, text: str, scope: str = "project_kb"):
    """Create a mock object with RetrievedChunk attributes."""
    chunk = MagicMock()
    chunk.document_title = doc_title
    chunk.text = text
    chunk.scope = scope
    chunk.chunk_id = str(uuid4())
    chunk.document_id = str(uuid4())
    chunk.document_type = "text/plain"
    chunk.chunk_index = 0
    chunk.section_path = None
    chunk.page_range = None
    chunk.similarity_score = 0.85
    chunk.token_count = 50
    return chunk


class TestL8ProjectKBChunks:
    """L8: Project KB retrieval returns chunks — rag_context_text and rag_chunks populated."""

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_l8_project_kb_chunks_returned(self, mock_retrieve, mock_select):
        from app.services.rag.framework_selection import FrameworkMatch

        mock_select.return_value = FrameworkMatch(None, None, None)

        project_chunk = _make_mock_chunk("Design Doc", "Use microservices", "project_kb")
        # Return chunks for project scope, empty for agent scope
        mock_retrieve.side_effect = [[project_chunk], []]

        mock_sb = _base_mock_sb_with_agent()
        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="architecture question",
        )

        assert len(result.rag_chunks) == 1
        assert "[Source: Design Doc]" in result.rag_context_text
        assert "Use microservices" in result.rag_context_text


class TestL9AgentKBChunks:
    """L9: Agent KB retrieval returns chunks."""

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_l9_agent_kb_chunks_returned(self, mock_retrieve, mock_select):
        from app.services.rag.framework_selection import FrameworkMatch

        mock_select.return_value = FrameworkMatch(None, None, None)

        agent_chunk = _make_mock_chunk("Agent Playbook", "Always empathize first", "agent_kb")
        # Empty for project scope, chunks for agent scope
        mock_retrieve.side_effect = [[], [agent_chunk]]

        mock_sb = _base_mock_sb_with_agent()
        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="coaching question",
        )

        assert len(result.rag_chunks) == 1
        assert "[Source: Agent Playbook]" in result.rag_context_text
        assert "Always empathize first" in result.rag_context_text


class TestL8L9BothScopes:
    """L8+L9: Both project and agent chunks combined in rag_chunks."""

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_l8_l9_both_scopes(self, mock_retrieve, mock_select):
        from app.services.rag.framework_selection import FrameworkMatch

        mock_select.return_value = FrameworkMatch(None, None, None)

        proj_chunk = _make_mock_chunk("Proj Doc", "Project info", "project_kb")
        agent_chunk = _make_mock_chunk("Agent Doc", "Agent info", "agent_kb")
        mock_retrieve.side_effect = [[proj_chunk], [agent_chunk]]

        mock_sb = _base_mock_sb_with_agent()
        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="combined question",
        )

        assert len(result.rag_chunks) == 2
        assert "[Source: Proj Doc]" in result.rag_context_text
        assert "[Source: Agent Doc]" in result.rag_context_text


class TestRAGNoChunks:
    """RAG: retrieve() returns [] — graceful empty."""

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_rag_no_chunks_above_threshold(self, mock_retrieve, mock_select):
        from app.services.rag.framework_selection import FrameworkMatch

        mock_select.return_value = FrameworkMatch(None, None, None)
        mock_retrieve.return_value = []  # No chunks from either scope

        mock_sb = _base_mock_sb_with_agent()
        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="obscure question",
        )

        assert result.rag_chunks == []
        assert result.rag_context_text == ""


# ---------------------------------------------------------------------------
# Conversation History Tests
# ---------------------------------------------------------------------------


def _base_mock_sb_company_only(messages_data=None, summary_data=None):
    """Return a mock supabase for a company-only conversation (no agent, no project).

    This avoids triggering L7/L8/L9 (which need an active agent/project).
    """
    return _build_mock_supabase({
        "conversations": [
            {"company_id": COMPANY_ID, "project_id": None, "active_agent_id": None},
        ],
        "users": [{"name": "HistUser", "email": "histuser@example.com", "bio": "Test"}],
        "companies": [{"name": "HistCo", "description": "History tests"}],
        "messages": [messages_data if messages_data is not None else []],
        "conversation_summaries": [summary_data if summary_data is not None else []],
    })


class TestConversationHistoryRecent:
    """Conversation history: 5 messages — all 5 in history."""

    @pytest.mark.asyncio
    async def test_conversation_history_recent_messages(self):
        messages = [
            {"role": "user", "content": "Hello", "sequence": 1},
            {"role": "assistant", "content": "Hi there!", "sequence": 2},
            {"role": "user", "content": "Question", "sequence": 3},
            {"role": "assistant", "content": "Answer", "sequence": 4},
            {"role": "user", "content": "Thanks", "sequence": 5},
        ]

        mock_sb = _base_mock_sb_company_only(messages_data=messages)
        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="test",
        )

        assert len(result.conversation_history) == 5
        assert result.conversation_history[0] == {"role": "user", "content": "Hello"}
        assert result.conversation_history[-1] == {"role": "user", "content": "Thanks"}


class TestConversationHistoryWithSummary:
    """Conversation history: summary exists + 25 messages — summary + last 20."""

    @pytest.mark.asyncio
    async def test_conversation_history_with_summary(self):
        messages = [
            {"role": "user", "content": f"Message {i}", "sequence": i}
            for i in range(1, 26)
        ]
        summary = [
            {"summary_text": "Earlier discussion about project goals.", "messages_covered_up_to": 5},
        ]

        mock_sb = _base_mock_sb_company_only(messages_data=messages, summary_data=summary)
        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="test",
        )

        # 1 summary + last 20 messages = 21 entries
        assert len(result.conversation_history) == 21
        assert result.conversation_history[0]["role"] == "system"
        assert "[Previous conversation summary]" in result.conversation_history[0]["content"]
        assert result.conversation_history[1]["role"] == "user"
        # Last 20 messages = messages 6..25
        assert result.conversation_history[1]["content"] == "Message 6"
        assert result.conversation_history[-1]["content"] == "Message 25"


class TestConversationHistoryEmpty:
    """Conversation history: no messages — empty list."""

    @pytest.mark.asyncio
    async def test_conversation_history_empty(self):
        mock_sb = _base_mock_sb_company_only(messages_data=[], summary_data=[])
        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="test",
        )

        assert result.conversation_history == []


# ---------------------------------------------------------------------------
# KIN-391: Framework user overrides — disabled, pinned, excluded
# ---------------------------------------------------------------------------

PINNED_FW_ID = str(uuid4())


class TestL7OverrideDisabled:
    """KIN-391: disabled=True skips L7 entirely — no pipeline call."""

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_disabled_skips_l7(self, mock_retrieve, mock_select):
        mock_retrieve.return_value = []

        mock_sb = _base_mock_sb_with_agent(
            framework_overrides={"pinned": [], "excluded": [], "disabled": True}
        )
        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="test with disabled",
        )

        # select_framework should NOT be called
        mock_select.assert_not_called()
        combined = "\n".join(result.system_parts)
        assert "[Framework:" not in combined


class TestL7OverridePinned:
    """KIN-391: pinned list bypasses pipeline, injects pinned frameworks."""

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.framework_selection.fetch_pinned_frameworks", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_pinned_bypasses_pipeline(self, mock_retrieve, mock_fetch_pinned, mock_select):
        from app.services.rag.framework_selection import FrameworkMatch

        mock_retrieve.return_value = []
        mock_fetch_pinned.return_value = [
            FrameworkMatch(
                matched_framework_id=PINNED_FW_ID,
                matched_framework_name="Pinned Framework",
                framework_text="Framework: Pinned Framework\n\nDescription: Force-injected",
            )
        ]

        mock_sb = _base_mock_sb_with_agent(
            framework_overrides={"pinned": [PINNED_FW_ID], "excluded": [], "disabled": False}
        )
        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="test with pinned",
        )

        # Pipeline NOT called, pinned fetch IS called
        mock_select.assert_not_called()
        mock_fetch_pinned.assert_called_once_with([PINNED_FW_ID], mock_sb)
        assert any("[Framework: Pinned Framework]" in p for p in result.system_parts)


class TestL7OverrideExcluded:
    """KIN-391: excluded list passed to pipeline as excluded_ids."""

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_excluded_passed_to_pipeline(self, mock_retrieve, mock_select):
        from app.services.rag.framework_selection import FrameworkMatch

        mock_retrieve.return_value = []
        mock_select.return_value = FrameworkMatch(None, None, None)

        excluded_fw_id = str(uuid4())
        mock_sb = _base_mock_sb_with_agent(
            framework_overrides={"pinned": [], "excluded": [excluded_fw_id], "disabled": False}
        )
        assembler = ContextAssembler()
        await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="test with excluded",
        )

        # Pipeline called with excluded_ids
        mock_select.assert_called_once()
        call_kwargs = mock_select.call_args
        assert call_kwargs.kwargs.get("excluded_ids") == {excluded_fw_id}


class TestL7OverrideNoInstance:
    """KIN-391: No agent_instance row → pipeline runs normally (empty overrides)."""

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_no_instance_runs_pipeline_normally(self, mock_retrieve, mock_select):
        from app.services.rag.framework_selection import FrameworkMatch

        mock_retrieve.return_value = []
        mock_select.return_value = FrameworkMatch(
            matched_framework_id="fw-normal",
            matched_framework_name="Normal Match",
            framework_text="Framework: Normal Match\n\nDescription: Selected normally",
        )

        # Second agent_instances call returns None (no instance found)
        mock_sb = _build_mock_supabase({
            "conversations": [
                {"company_id": COMPANY_ID, "project_id": PROJECT_ID, "active_agent_id": AGENT_DEF_ID},
            ],
            "users": [{"name": "Tester", "email": "tester@example.com", "bio": "QA"}],
            "companies": [{"name": "TestCo", "description": "Testing"}],
            "projects": [{"instructions": "Test instructions"}],
            "active_memory_entries": [
                [{"content": "project memory"}],
                [{"content": "agent memory"}],
            ],
            "agent_definitions": [{"name": "TestAgent", "instructions": "Be helpful"}],
            # First call: L6 instance lookup, second: overrides lookup returns None
            "agent_instances": [
                {"id": AGENT_INSTANCE_ID},
                None,
            ],
            "messages": [[]],
            "conversation_summaries": [[]],
        })

        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            query_text="test no instance",
        )

        # Pipeline runs normally with no excluded_ids
        mock_select.assert_called_once()
        call_kwargs = mock_select.call_args
        assert call_kwargs.kwargs.get("excluded_ids") is None
        assert any("[Framework: Normal Match]" in p for p in result.system_parts)


# ---------------------------------------------------------------------------
# KIN-485 — Component D: date-aware source-line formatting
# ---------------------------------------------------------------------------

from datetime import date  # noqa: E402

from app.services.context_assembler import _format_source_header  # noqa: E402


def _make_dated_chunk(title: str, effective_date, *, date_is_estimated: bool):
    """Mock chunk carrying date metadata (mirrors RetrievedChunk shape)."""
    chunk = MagicMock()
    chunk.document_title = title
    chunk.effective_date = effective_date
    chunk.date_is_estimated = date_is_estimated
    chunk.text = "body"
    return chunk


class TestRecencyOffStateByteIdentical:
    """RECENCY_ENABLED=False must produce the pre-feature `[Source: TITLE]` exactly."""

    def test_off_state_with_real_date_strips_date(self):
        chunk = _make_dated_chunk("Design Doc", date(2026, 5, 1), date_is_estimated=False)
        assert _format_source_header(chunk, recency_enabled=False) == "[Source: Design Doc]"

    def test_off_state_with_estimated_date_strips_date(self):
        chunk = _make_dated_chunk("Stale Doc", date(2024, 1, 1), date_is_estimated=True)
        assert _format_source_header(chunk, recency_enabled=False) == "[Source: Stale Doc]"

    def test_off_state_with_none_date(self):
        chunk = _make_dated_chunk("No Date Doc", None, date_is_estimated=False)
        assert _format_source_header(chunk, recency_enabled=False) == "[Source: No Date Doc]"


class TestRecencyOnStateDateLabel:
    """RECENCY_ENABLED=True appends `Published:`/`Added:` per estimated flag."""

    def test_on_state_published_when_not_estimated(self):
        chunk = _make_dated_chunk("Fresh Doc", date(2026, 5, 23), date_is_estimated=False)
        result = _format_source_header(chunk, recency_enabled=True)
        assert result == "[Source: Fresh Doc, Published: 2026-05-23]"

    def test_on_state_added_when_estimated(self):
        chunk = _make_dated_chunk("Ingest Doc", date(2024, 11, 4), date_is_estimated=True)
        result = _format_source_header(chunk, recency_enabled=True)
        assert result == "[Source: Ingest Doc, Added: 2024-11-04]"

    def test_on_state_with_none_date_omits_suffix(self):
        # Fallback search path: no dates selected → defensive omit, no garbage.
        chunk = _make_dated_chunk("Fallback Doc", None, date_is_estimated=False)
        assert _format_source_header(chunk, recency_enabled=True) == "[Source: Fallback Doc]"


class TestRecencyAssembleEndToEnd:
    """Full assemble() path: rag_context_text byte-identical off; date-tagged on."""

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_assemble_off_state_byte_identical(self, mock_retrieve, mock_select):
        """RECENCY_ENABLED=False → rag_context_text drops date even when chunk carries it."""
        from app.services.rag.framework_selection import FrameworkMatch

        mock_select.return_value = FrameworkMatch(None, None, None)
        chunk = _make_dated_chunk("Dated Doc", date(2026, 5, 1), date_is_estimated=False)
        chunk.scope = "project_kb"
        chunk.chunk_id = str(uuid4())
        chunk.document_id = str(uuid4())
        chunk.document_type = "text/plain"
        chunk.chunk_index = 0
        chunk.section_path = None
        chunk.page_range = None
        chunk.similarity_score = 0.85
        chunk.token_count = 50
        chunk.text = "Some content"
        mock_retrieve.side_effect = [[chunk], []]

        mock_sb = _base_mock_sb_with_agent()
        with patch("app.core.config.settings.RECENCY_ENABLED", False):
            result = await ContextAssembler().assemble(
                supabase=mock_sb,
                user_id=USER_ID,
                conversation_id=CONVERSATION_ID,
                query_text="date question",
            )
        assert "[Source: Dated Doc]\nSome content" in result.rag_context_text
        assert "Published" not in result.rag_context_text
        assert "Added" not in result.rag_context_text

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_assemble_on_state_appends_date(self, mock_retrieve, mock_select):
        """RECENCY_ENABLED=True → header line carries `Published: YYYY-MM-DD`."""
        from app.services.rag.framework_selection import FrameworkMatch

        mock_select.return_value = FrameworkMatch(None, None, None)
        chunk = _make_dated_chunk("Dated Doc", date(2026, 5, 1), date_is_estimated=False)
        chunk.scope = "project_kb"
        chunk.chunk_id = str(uuid4())
        chunk.document_id = str(uuid4())
        chunk.document_type = "text/plain"
        chunk.chunk_index = 0
        chunk.section_path = None
        chunk.page_range = None
        chunk.similarity_score = 0.85
        chunk.token_count = 50
        chunk.text = "Some content"
        mock_retrieve.side_effect = [[chunk], []]

        mock_sb = _base_mock_sb_with_agent()
        with patch("app.core.config.settings.RECENCY_ENABLED", True):
            result = await ContextAssembler().assemble(
                supabase=mock_sb,
                user_id=USER_ID,
                conversation_id=CONVERSATION_ID,
                query_text="date question",
            )
        assert "[Source: Dated Doc, Published: 2026-05-01]" in result.rag_context_text

    @pytest.mark.asyncio
    @patch("app.services.rag.framework_selection.select_framework", new_callable=AsyncMock)
    @patch("app.services.rag.retrieval.retrieve", new_callable=AsyncMock)
    async def test_assemble_on_state_estimated_date_uses_added_label(self, mock_retrieve, mock_select):
        """RECENCY_ENABLED=True + date_is_estimated=True → header carries `Added: YYYY-MM-DD`."""
        from app.services.rag.framework_selection import FrameworkMatch

        mock_select.return_value = FrameworkMatch(None, None, None)
        chunk = _make_dated_chunk("Estimated Doc", date(2026, 5, 1), date_is_estimated=True)
        chunk.scope = "project_kb"
        chunk.chunk_id = str(uuid4())
        chunk.document_id = str(uuid4())
        chunk.document_type = "text/plain"
        chunk.chunk_index = 0
        chunk.section_path = None
        chunk.page_range = None
        chunk.similarity_score = 0.85
        chunk.token_count = 50
        chunk.text = "Some content"
        mock_retrieve.side_effect = [[chunk], []]

        mock_sb = _base_mock_sb_with_agent()
        with patch("app.core.config.settings.RECENCY_ENABLED", True):
            result = await ContextAssembler().assemble(
                supabase=mock_sb,
                user_id=USER_ID,
                conversation_id=CONVERSATION_ID,
                query_text="date question",
            )
        assert "[Source: Estimated Doc, Added: 2026-05-01]" in result.rag_context_text
        assert "Published" not in result.rag_context_text


class TestRecencyPromptVariantSelection:
    """generation.py picks v1 vs v2 system prompt based on RECENCY_ENABLED."""

    def test_v1_prompt_is_byte_identical_to_pre_feature(self):
        # If anyone edits v1 they break the byte-identical off-state guarantee.
        from app.services.prompts import get_prompt

        expected = (
            "You are a helpful AI assistant. Use the context provided below to inform your responses. "
            "Always prioritize information from the context layers when relevant to the user's question.\n\n"
            "{context_layers}\n\n"
            "{rag_context}"
        )
        assert get_prompt("context-stack-system-v1", "system") == expected

    def test_v2_prompt_includes_contradiction_instruction(self):
        from app.services.prompts import get_prompt

        v2 = get_prompt("context-stack-system-v2", "system")
        assert "Sources are labeled with publication dates" in v2
        assert "prefer the more recent one" in v2
        # v2 must still expose the same template variables v1 does so the
        # generation.py format() call stays interchangeable.
        assert "{context_layers}" in v2
        assert "{rag_context}" in v2
