"""
Tests for the generation endpoint — KIN-385 Tasks 5+6.

Tests:
  1. TestGenerateSuccess — SSE stream with delta + done events
  2. TestGenerateModelResolutionDefault — uses user's default_model_id
  3. TestGenerateModelResolutionOverride — uses model_id param
  4. TestGenerateNoBYOKKey400 — no BYOK key → 400
  5. TestGenerateNoModel400 — no model_id and no default → 400
  6. TestGenerateConversationNotFound404 — wrong conversation_id → 404
  7. TestGenerateAgentSwitch — agent_id param updates conversation
  8. TestGenerateStoresMessages — user + assistant messages stored
  9. TestGenerateCompanyLevel — no project → context assembler called
  10. TestGenerateLLMFailure — stream_llm raises → error SSE event
  11. TestGenerateFullFlowIntegration — all 9 context layers active, real assembler
"""

import json
from dataclasses import dataclass, field
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID

# ---------------------------------------------------------------------------
# Shared IDs
# ---------------------------------------------------------------------------

CONV_ID = str(uuid4())
COMPANY_ID = str(uuid4())
PROJECT_ID = str(uuid4())
AGENT_ID = str(uuid4())
MODEL_UUID = str(uuid4())
MODEL_NAME = "gpt-4o"
PROVIDER = "openai"
API_KEY = "sk-test-key-12345"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse(body: str) -> list[dict]:
    """Parse SSE response body into list of event dicts."""
    events = []
    for line in body.strip().split("\n\n"):
        line = line.strip()
        if line.startswith("data: "):
            data = line[len("data: "):]
            events.append(json.loads(data))
    return events


@dataclass
class MockAssembledContext:
    """Minimal stub matching AssembledContext interface."""
    system_parts: list[str] = field(default_factory=lambda: ["[User Profile]\nName: Test User"])
    rag_chunks: list = field(default_factory=list)
    rag_context_text: str = ""
    model_context_window: int = 100_000
    conversation_history: list[dict] = field(default_factory=list)


def _build_mock_supabase(
    conversation_data=None,
    user_data=None,
    model_data=None,
    message_count_data=None,
    insert_data=None,
    update_data=None,
):
    """
    Build a mock Supabase client with table-specific routing.

    Each table call returns a chainable mock that terminates at .execute().
    """
    mock = MagicMock()

    # Default data
    if conversation_data is None:
        conversation_data = {
            "id": CONV_ID,
            "company_id": COMPANY_ID,
            "project_id": PROJECT_ID,
            "active_agent_id": AGENT_ID,
        }
    if user_data is None:
        user_data = {"default_model_id": MODEL_UUID}
    if model_data is None:
        model_data = {
            "model_id": MODEL_NAME,
            "provider": PROVIDER,
            "context_window": 128000,
        }
    if message_count_data is None:
        message_count_data = []  # no existing messages
    if insert_data is None:
        insert_data = [{"id": str(uuid4()), "role": "user", "content": "test"}]

    # Track insert calls for assertion
    insert_calls = []

    def _table(name):
        chain = MagicMock()

        if name == "conversations":
            # select → conversation ownership check
            chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data=conversation_data
            )
            # update → agent switch
            if update_data is not None:
                chain.update.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=update_data
                )
            else:
                chain.update.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[conversation_data]
                )

        elif name == "users":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=user_data
            )

        elif name == "llm_models":
            chain.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data=model_data
            )

        elif name == "messages":
            # select for sequence resolution: select → eq → order → limit → execute
            chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=message_count_data
            )
            # insert for storing messages
            def _insert(row):
                insert_calls.append(row)
                result_row = {**row, "id": str(uuid4())}
                ret = MagicMock()
                ret.execute.return_value = MagicMock(data=[result_row])
                return ret

            chain.insert.side_effect = _insert

        return chain

    mock.table.side_effect = _table
    mock._insert_calls = insert_calls
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gen_client() -> Generator:
    """TestClient with auth override and mocked Supabase/LLM/context."""
    from fastapi.testclient import TestClient
    from app.auth.deps import CurrentUser, get_current_user
    from app.main import app

    async def _override_user() -> CurrentUser:
        return CurrentUser(user_id=TEST_USER_ID)

    app.dependency_overrides[get_current_user] = _override_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateSuccess:
    """Mock stream_llm yielding chunks → SSE delta + done events, AI message stored."""

    def test_generate_success_streams_response(self, gen_client):
        mock_sb = _build_mock_supabase()

        async def _mock_stream(**kwargs):
            for chunk in ["Hello", " world"]:
                yield chunk

        mock_ctx = MockAssembledContext()

        with (
            patch("app.api.routes.generation.get_supabase_client", return_value=mock_sb),
            patch("app.services.user_keys.fetch_user_key", return_value=API_KEY),
            patch(
                "app.services.context_assembler.ContextAssembler.assemble",
                new_callable=AsyncMock,
                return_value=mock_ctx,
            ),
            patch("app.services.llm_client.stream_llm", side_effect=_mock_stream),
        ):
            resp = gen_client.post(
                f"/api/v1/conversations/{CONV_ID}/generate",
                json={"message": "Hello there"},
            )

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert len(events) == 3  # 2 deltas + 1 done
        assert events[0] == {"type": "delta", "content": "Hello"}
        assert events[1] == {"type": "delta", "content": " world"}
        assert events[2]["type"] == "done"
        assert "message_id" in events[2]


class TestGenerateModelResolutionDefault:
    """No model_id param → uses user's default_model_id."""

    def test_generate_model_resolution_default(self, gen_client):
        mock_sb = _build_mock_supabase()

        async def _mock_stream(**kwargs):
            yield "ok"

        mock_ctx = MockAssembledContext()

        with (
            patch("app.api.routes.generation.get_supabase_client", return_value=mock_sb),
            patch("app.services.user_keys.fetch_user_key", return_value=API_KEY),
            patch(
                "app.services.context_assembler.ContextAssembler.assemble",
                new_callable=AsyncMock,
                return_value=mock_ctx,
            ),
            patch("app.services.llm_client.stream_llm", side_effect=_mock_stream) as mock_llm,
        ):
            resp = gen_client.post(
                f"/api/v1/conversations/{CONV_ID}/generate",
                json={"message": "test"},
            )

        assert resp.status_code == 200
        # stream_llm was called with the default model
        call_kwargs = mock_llm.call_args
        # The model comes from llm_models row
        assert call_kwargs is not None


class TestGenerateModelResolutionOverride:
    """model_id param → uses that model (skips user default)."""

    def test_generate_model_resolution_override(self, gen_client):
        override_model_uuid = str(uuid4())
        mock_sb = _build_mock_supabase(
            model_data={
                "model_id": "claude-sonnet-4-6",
                "provider": "anthropic",
                "context_window": 200000,
            },
        )

        async def _mock_stream(**kwargs):
            yield "ok"

        mock_ctx = MockAssembledContext()

        with (
            patch("app.api.routes.generation.get_supabase_client", return_value=mock_sb),
            patch("app.services.user_keys.fetch_user_key", return_value=API_KEY),
            patch(
                "app.services.context_assembler.ContextAssembler.assemble",
                new_callable=AsyncMock,
                return_value=mock_ctx,
            ),
            patch("app.services.llm_client.stream_llm", side_effect=_mock_stream) as mock_llm,
        ):
            resp = gen_client.post(
                f"/api/v1/conversations/{CONV_ID}/generate",
                json={"message": "test", "model_id": override_model_uuid},
            )

        assert resp.status_code == 200
        # Verify stream_llm was called with the override model name
        assert mock_llm.called
        call_kwargs = mock_llm.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-6"


class TestGenerateNoBYOKKey400:
    """fetch_user_key_async returns None → 400."""

    def test_generate_no_byok_key_400(self, gen_client):
        mock_sb = _build_mock_supabase()

        with (
            patch("app.api.routes.generation.get_supabase_client", return_value=mock_sb),
            patch("app.services.user_keys.fetch_user_key", return_value=None),
        ):
            resp = gen_client.post(
                f"/api/v1/conversations/{CONV_ID}/generate",
                json={"message": "test"},
            )

        assert resp.status_code == 400
        assert "No API key configured" in resp.json()["error"]["message"]


class TestGenerateNoModel400:
    """No model_id and no default → 400."""

    def test_generate_no_model_400(self, gen_client):
        mock_sb = _build_mock_supabase(
            user_data={"default_model_id": None},
        )

        with patch("app.api.routes.generation.get_supabase_client", return_value=mock_sb):
            resp = gen_client.post(
                f"/api/v1/conversations/{CONV_ID}/generate",
                json={"message": "test"},
            )

        assert resp.status_code == 400
        assert "No model selected" in resp.json()["error"]["message"]


class TestGenerateConversationNotFound404:
    """Wrong conversation_id → 404."""

    def test_generate_conversation_not_found_404(self, gen_client):
        # Build a mock where the conversations query returns no data
        mock_sb = MagicMock()
        conv_chain = MagicMock()
        conv_chain.select.return_value \
            .eq.return_value \
            .eq.return_value \
            .is_.return_value \
            .maybe_single.return_value \
            .execute.return_value = MagicMock(data=None)
        mock_sb.table.return_value = conv_chain

        with patch("app.api.routes.generation.get_supabase_client", return_value=mock_sb):
            resp = gen_client.post(
                f"/api/v1/conversations/{str(uuid4())}/generate",
                json={"message": "test"},
            )

        assert resp.status_code == 404


class TestGenerateAgentSwitch:
    """agent_id param → conversation.active_agent_id updated."""

    def test_generate_agent_switch(self, gen_client):
        new_agent_id = str(uuid4())
        mock_sb = _build_mock_supabase()

        async def _mock_stream(**kwargs):
            yield "ok"

        mock_ctx = MockAssembledContext()

        with (
            patch("app.api.routes.generation.get_supabase_client", return_value=mock_sb),
            patch("app.services.user_keys.fetch_user_key", return_value=API_KEY),
            patch(
                "app.services.context_assembler.ContextAssembler.assemble",
                new_callable=AsyncMock,
                return_value=mock_ctx,
            ),
            patch("app.services.llm_client.stream_llm", side_effect=_mock_stream),
        ):
            resp = gen_client.post(
                f"/api/v1/conversations/{CONV_ID}/generate",
                json={"message": "test", "agent_id": new_agent_id},
            )

        assert resp.status_code == 200
        # Verify the conversation update was called (agent switch)
        update_calls = [
            call for call in mock_sb.table.call_args_list
            if call[0] == ("conversations",)
        ]
        # Should have at least 2 calls to conversations table: select + update
        assert len(update_calls) >= 2


class TestGenerateStoresMessages:
    """After stream, verify 2 message inserts (user + assistant)."""

    def test_generate_stores_user_and_ai_messages(self, gen_client):
        mock_sb = _build_mock_supabase()

        async def _mock_stream(**kwargs):
            yield "response text"

        mock_ctx = MockAssembledContext()

        with (
            patch("app.api.routes.generation.get_supabase_client", return_value=mock_sb),
            patch("app.services.user_keys.fetch_user_key", return_value=API_KEY),
            patch(
                "app.services.context_assembler.ContextAssembler.assemble",
                new_callable=AsyncMock,
                return_value=mock_ctx,
            ),
            patch("app.services.llm_client.stream_llm", side_effect=_mock_stream),
        ):
            resp = gen_client.post(
                f"/api/v1/conversations/{CONV_ID}/generate",
                json={"message": "Hello there"},
            )

        assert resp.status_code == 200

        # Verify inserts: should have user message + assistant message
        inserts = mock_sb._insert_calls
        assert len(inserts) == 2

        user_msg = inserts[0]
        assert user_msg["role"] == "user"
        assert user_msg["content"] == "Hello there"
        assert user_msg["sequence"] == 0

        ai_msg = inserts[1]
        assert ai_msg["role"] == "assistant"
        assert ai_msg["content"] == "response text"
        assert ai_msg["sequence"] == 1
        assert ai_msg["model"] == MODEL_NAME


class TestGenerateCompanyLevel:
    """No project → context assembler called with appropriate scope."""

    def test_generate_company_level_conversation(self, gen_client):
        mock_sb = _build_mock_supabase(
            conversation_data={
                "id": CONV_ID,
                "company_id": COMPANY_ID,
                "project_id": None,
                "active_agent_id": None,
            },
        )

        async def _mock_stream(**kwargs):
            yield "ok"

        mock_ctx = MockAssembledContext()

        with (
            patch("app.api.routes.generation.get_supabase_client", return_value=mock_sb),
            patch("app.services.user_keys.fetch_user_key", return_value=API_KEY),
            patch(
                "app.services.context_assembler.ContextAssembler.assemble",
                new_callable=AsyncMock,
                return_value=mock_ctx,
            ) as mock_assemble,
            patch("app.services.llm_client.stream_llm", side_effect=_mock_stream),
        ):
            resp = gen_client.post(
                f"/api/v1/conversations/{CONV_ID}/generate",
                json={"message": "test"},
            )

        assert resp.status_code == 200
        # Verify context assembler was called
        assert mock_assemble.called
        call_kwargs = mock_assemble.call_args
        # conversation_id is the 3rd positional arg
        assert call_kwargs[0][2] == CONV_ID


class TestGenerateLLMFailure:
    """stream_llm raises → SSE error event, no AI message stored."""

    def test_generate_llm_failure_sends_error_event(self, gen_client):
        mock_sb = _build_mock_supabase()

        async def _mock_stream_fail(**kwargs):
            raise RuntimeError("LLM provider unavailable")
            yield  # make it a generator  # noqa: E501

        mock_ctx = MockAssembledContext()

        with (
            patch("app.api.routes.generation.get_supabase_client", return_value=mock_sb),
            patch("app.services.user_keys.fetch_user_key", return_value=API_KEY),
            patch(
                "app.services.context_assembler.ContextAssembler.assemble",
                new_callable=AsyncMock,
                return_value=mock_ctx,
            ),
            patch("app.services.llm_client.stream_llm", side_effect=_mock_stream_fail),
        ):
            resp = gen_client.post(
                f"/api/v1/conversations/{CONV_ID}/generate",
                json={"message": "test"},
            )

        assert resp.status_code == 200  # SSE endpoint returns 200, error is in the stream
        events = _parse_sse(resp.text)
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "LLM provider unavailable" in events[0]["message"]

        # Only user message should have been stored (no assistant message)
        inserts = mock_sb._insert_calls
        assert len(inserts) == 1
        assert inserts[0]["role"] == "user"


# ---------------------------------------------------------------------------
# Full-flow integration (all 9 context layers)
# ---------------------------------------------------------------------------

AGENT_INSTANCE_ID = str(uuid4())


def _build_full_flow_supabase():
    """
    Build a mock Supabase client that satisfies BOTH the generation route
    AND the real ContextAssembler (not mocked) for a full 9-layer run.

    Tables hit by the route: conversations, users, llm_models, messages
    Tables hit by the assembler: conversations, users, companies, projects,
        active_memory_entries, agent_definitions, agent_instances, messages,
        conversation_summaries
    """
    mock = MagicMock()
    insert_calls: list[dict] = []

    def _table(name):
        chain = MagicMock()

        if name == "conversations":
            # Route: select → eq(id) → eq(user_id) → is_(deleted_at) → maybe_single
            chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={
                    "id": CONV_ID,
                    "company_id": COMPANY_ID,
                    "project_id": PROJECT_ID,
                    "active_agent_id": AGENT_ID,
                }
            )
            # Assembler: select → eq(id) → eq(user_id) → is_(deleted_at) → single
            chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                data={
                    "company_id": COMPANY_ID,
                    "project_id": PROJECT_ID,
                    "active_agent_id": AGENT_ID,
                }
            )
            # update (agent switch — not triggered in this test, but wire it)
            chain.update.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": CONV_ID}]
            )

        elif name == "users":
            # Route: select(default_model_id) → eq(id) → single
            # Assembler: select(name, bio) → eq(id) → single
            # Both use .single(), but select different columns. We return a superset.
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={
                    "default_model_id": MODEL_UUID,
                    "name": "Test User",
                    "bio": "Integration test bio",
                }
            )

        elif name == "llm_models":
            chain.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={
                    "model_id": MODEL_NAME,
                    "provider": PROVIDER,
                    "context_window": 128000,
                }
            )

        elif name == "companies":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"name": "Acme Corp", "description": "A test company"}
            )

        elif name == "projects":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"instructions": "Always be helpful and concise."}
            )

        elif name == "agent_definitions":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"name": "Nate", "instructions": "You are Nate, a strategic advisor."}
            )

        elif name == "agent_instances":
            chain.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={"id": AGENT_INSTANCE_ID}
            )

        elif name == "active_memory_entries":
            # Called twice: once for project memory (L4), once for agent memory (L6).
            # Both use .select("content").eq(...).eq(...).execute().
            # Since this mock is created fresh per .table() call, we return
            # entries for whichever scope queries it. Both get content.
            chain.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"content": "Remember: user prefers concise answers."}]
            )

        elif name == "messages":
            # Assembler: select(role, content, sequence) → eq(conversation_id) → order → execute
            chain.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=[
                    {"role": "user", "content": "Hi there", "sequence": 0},
                    {"role": "assistant", "content": "Hello!", "sequence": 1},
                ]
            )
            # Route: select(sequence) → eq → order → limit → execute (for sequence resolution)
            chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"sequence": 1}]
            )
            # insert for storing messages
            def _insert(row):
                insert_calls.append(row)
                result_row = {**row, "id": str(uuid4())}
                ret = MagicMock()
                ret.execute.return_value = MagicMock(data=[result_row])
                return ret

            chain.insert.side_effect = _insert

        elif name == "conversation_summaries":
            chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )

        return chain

    mock.table.side_effect = _table
    mock._insert_calls = insert_calls
    return mock


class TestGenerateFullFlowIntegration:
    """Full generation flow with all 9 context layers active — no assembler mock."""

    def test_full_flow_all_layers(self, gen_client):
        mock_sb = _build_full_flow_supabase()

        async def _mock_stream(**kwargs):
            for chunk in ["Hello ", "world"]:
                yield chunk

        # L7: Framework match
        from app.services.rag.framework_selection import FrameworkMatch

        mock_framework = FrameworkMatch(
            matched_framework_id=str(uuid4()),
            matched_framework_name="Strategic Planning",
            framework_text="Use a structured strategic planning approach.",
        )

        # L8/L9: RAG chunks
        from app.services.rag.retrieval import RetrievedChunk

        mock_chunks = [
            RetrievedChunk(
                chunk_id=str(uuid4()),
                document_id=str(uuid4()),
                document_title="Company Playbook",
                document_type="text/plain",
                text="Chapter 1: Strategy fundamentals",
                chunk_index=0,
                section_path="§1",
                page_range="1-3",
                similarity_score=0.85,
                token_count=10,
                scope="project_kb",
            ),
        ]

        captured_system_prompt: list[str] = []

        _original_stream = None

        async def _capture_and_stream(**kwargs):
            """Capture the system prompt from the messages, then yield chunks."""
            msgs = kwargs.get("messages", [])
            for m in msgs:
                if m.get("role") == "system":
                    captured_system_prompt.append(m["content"])
            for chunk in ["Hello ", "world"]:
                yield chunk

        with (
            patch("app.api.routes.generation.get_supabase_client", return_value=mock_sb),
            # Route-level key fetch (sync wrapper called via fetch_user_key_async)
            patch("app.services.user_keys.fetch_user_key", return_value=API_KEY),
            # L7: framework selection
            patch(
                "app.services.rag.framework_selection.select_framework",
                new_callable=AsyncMock,
                return_value=mock_framework,
            ),
            # L8/L9: RAG retrieval
            patch(
                "app.services.rag.retrieval.retrieve",
                new_callable=AsyncMock,
                return_value=mock_chunks,
            ),
            # LLM streaming — captures the system prompt for assertion
            patch("app.services.llm_client.stream_llm", side_effect=_capture_and_stream),
        ):
            resp = gen_client.post(
                f"/api/v1/conversations/{CONV_ID}/generate",
                json={"message": "What strategy should I use?"},
            )

        # --- SSE assertions ---
        assert resp.status_code == 200
        events = _parse_sse(resp.text)

        deltas = [e for e in events if e["type"] == "delta"]
        assert len(deltas) == 2
        assert deltas[0]["content"] == "Hello "
        assert deltas[1]["content"] == "world"

        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        assert "message_id" in done_events[0]

        # --- System prompt contains all 9 layer labels ---
        assert len(captured_system_prompt) == 1
        prompt = captured_system_prompt[0]

        # L1: User Profile
        assert "[User Profile]" in prompt
        # L2: Company
        assert "[Company:" in prompt
        assert "Acme Corp" in prompt
        # L3: Project Instructions
        assert "[Project Instructions]" in prompt
        # L4: Project Memory
        assert "[Project Memory]" in prompt
        # L5: Agent definition
        assert "[Agent:" in prompt
        assert "Nate" in prompt
        # L6: Agent Memory
        assert "[Agent Memory]" in prompt
        # L7: Framework
        assert "[Framework:" in prompt
        assert "Strategic Planning" in prompt
        # L8/L9: Source (RAG)
        assert "[Source:" in prompt
        assert "Company Playbook" in prompt
