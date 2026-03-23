"""
Unit tests for context_stack.assemble() — KIN-275.

Covers:
- L1 (user bio), L2 (company), L3 (project instructions) fetching + formatting
- L4, L5, L6, L7, L9 are stubs (empty strings) in Sprint 3
- L8 (project RAG) active when project_id present
- History: plain messages when no summary exists
- History: summary + verbatim window when summary exists (ADR-004)
- Token budget enforcement (truncation priority order)
- Company-scope conversation (no project_id) → L3/L8 empty
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.context_stack import ContextStack, _count_tokens, _enforce_budget, assemble


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_supabase(responses: dict[str, MagicMock]) -> MagicMock:
    """Supabase mock that dispatches .execute() results by table name.

    responses: {"table_name": MagicMock(data=...)}
    The last table() call wins if the same table is queried twice and not re-configured.
    """
    sb = MagicMock()
    current_table: list[str] = [""]

    def _table(name: str):
        current_table[0] = name
        return sb

    sb.table.side_effect = _table
    sb.select.return_value = sb
    sb.eq.return_value = sb
    sb.neq.return_value = sb
    sb.in_.return_value = sb
    sb.is_.return_value = sb
    sb.order.return_value = sb
    sb.limit.return_value = sb
    sb.maybe_single.return_value = sb
    sb.insert.return_value = sb
    sb.update.return_value = sb

    def _execute():
        table = current_table[0]
        return responses.get(table, MagicMock(data=None))

    sb.execute.side_effect = _execute
    return sb


def _result(data) -> MagicMock:
    r = MagicMock()
    r.data = data
    return r


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


CONV_PROJECT = _result({
    "project_id": "proj-1",
    "company_id": "comp-1",
    "active_agent_id": None,
})

CONV_COMPANY = _result({
    "project_id": None,
    "company_id": "comp-1",
    "active_agent_id": None,
})

USER_BIO = _result({"bio": "Experienced software engineer"})
COMPANY = _result({"name": "Acme Corp", "description": "A widget company"})
PROJECT = _result({"name": "Atlas", "instructions": "Always use TDD."})
NO_SUMMARY = _result(None)
MESSAGES = _result([
    {"role": "user", "content": "Hello!", "sequence": 0},
    {"role": "assistant", "content": "Hi there!", "sequence": 1},
])
EMPTY_MESSAGES = _result([])


# ---------------------------------------------------------------------------
# Tests — Layer fetching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_project_scope_all_layers():
    """Project conversation: L1, L2, L3, L8 populated; L4-7, L9 are stubs."""
    sb = _make_supabase({
        "conversations": CONV_PROJECT,
        "users": USER_BIO,
        "companies": COMPANY,
        "projects": PROJECT,
        "conversation_summaries": NO_SUMMARY,
        "messages": MESSAGES,
    })

    with patch("app.services.context_stack._fetch_l1", new_callable=AsyncMock, return_value="[User Profile]\nExperienced software engineer") as _l1, \
         patch("app.services.context_stack._fetch_l2", new_callable=AsyncMock, return_value="[Company: Acme Corp]\nA widget company") as _l2, \
         patch("app.services.context_stack._fetch_l3", new_callable=AsyncMock, return_value="[Project Instructions — Atlas]\nAlways use TDD.") as _l3, \
         patch("app.services.rag_service.retrieve_for_project", new_callable=AsyncMock, return_value="[Project Knowledge Base]\nChunk 1") as _rag:

        stack = await assemble(
            conversation_id="conv-1",
            user_id="user-1",
            query="How do I test?",
            model_context_window=100_000,
            supabase=sb,
        )

    assert "[User Profile]" in stack.l1_user_bio
    assert "[Company: Acme Corp]" in stack.l2_company
    assert "[Project Instructions" in stack.l3_project_instructions
    assert stack.l4_project_active_memory == ""
    assert stack.l5_agent_system_prompt == ""
    assert stack.l6_agent_active_memory == ""
    assert stack.l7_framework == ""
    assert stack.l9_agent_rag == ""
    assert len(stack.history) == 2
    assert stack.total_tokens > 0


@pytest.mark.asyncio
async def test_assemble_company_scope_no_l3_l8():
    """Company-scope conversation: L3 and L8 must remain empty."""
    sb = _make_supabase({
        "conversations": CONV_COMPANY,
        "users": USER_BIO,
        "companies": COMPANY,
        "conversation_summaries": NO_SUMMARY,
        "messages": MESSAGES,
    })

    with patch("app.services.context_stack._fetch_l1", new_callable=AsyncMock, return_value="[User Profile]\nBio") as _l1, \
         patch("app.services.context_stack._fetch_l2", new_callable=AsyncMock, return_value="[Company: Acme]") as _l2:

        stack = await assemble(
            conversation_id="conv-1",
            user_id="user-1",
            query="anything",
            model_context_window=100_000,
            supabase=sb,
        )

    assert stack.l3_project_instructions == ""
    assert stack.l8_project_rag == ""


@pytest.mark.asyncio
async def test_assemble_missing_conversation_returns_empty_stack():
    """If conversation not found, return empty ContextStack."""
    sb = _make_supabase({"conversations": _result(None)})

    stack = await assemble(
        conversation_id="nonexistent",
        user_id="user-1",
        query="q",
        model_context_window=100_000,
        supabase=sb,
    )
    assert stack == ContextStack()


@pytest.mark.asyncio
async def test_assemble_empty_bio_returns_empty_l1():
    """If user has no bio, L1 should be empty string."""
    sb = _make_supabase({
        "conversations": CONV_COMPANY,
        "users": _result({"bio": ""}),
        "companies": COMPANY,
        "conversation_summaries": NO_SUMMARY,
        "messages": EMPTY_MESSAGES,
    })

    with patch("app.services.context_stack._fetch_l1", new_callable=AsyncMock, return_value="") as _l1, \
         patch("app.services.context_stack._fetch_l2", new_callable=AsyncMock, return_value="[Company: Acme]") as _l2:

        stack = await assemble(
            conversation_id="conv-1",
            user_id="user-1",
            query="q",
            model_context_window=100_000,
            supabase=sb,
        )

    assert stack.l1_user_bio == ""


# ---------------------------------------------------------------------------
# Tests — History with summary injection (ADR-004)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_with_summary_and_verbatim_window():
    """When a summary exists, history = [summary_msg] + verbatim_window messages."""
    from app.services.context_stack import _fetch_history

    summary_result = _result([{
        "summary_text": "User asked about testing.",
        "messages_covered_up_to": 5,
    }])
    messages_result = _result([
        {"role": "user", "content": "old msg", "sequence": 3},
        {"role": "assistant", "content": "old reply", "sequence": 4},
        {"role": "user", "content": "recent msg", "sequence": 6},
        {"role": "assistant", "content": "recent reply", "sequence": 7},
    ])

    call_count = [0]

    def _execute():
        call_count[0] += 1
        if call_count[0] == 1:
            return summary_result
        return messages_result

    sb = MagicMock()
    sb.table.return_value = sb
    sb.select.return_value = sb
    sb.eq.return_value = sb
    sb.in_.return_value = sb
    sb.order.return_value = sb
    sb.limit.return_value = sb
    sb.execute.side_effect = _execute

    with patch("app.config.get_settings") as mock_settings:
        mock_settings.return_value.VERBATIM_WINDOW = 2

        async def _db(fn):
            return fn()

        history = await _fetch_history(_db, sb, "conv-1")

    assert history[0]["role"] == "system"
    assert "User asked about testing." in history[0]["content"]
    assert len(history) > 1
    # Verbatim window = 2, messages after sequence 5 = sequences 6,7
    user_msgs = [h for h in history[1:] if h["role"] == "user"]
    assert any("recent msg" in m["content"] for m in user_msgs)


# ---------------------------------------------------------------------------
# Tests — Token budget enforcement
# ---------------------------------------------------------------------------


def test_count_tokens_basic():
    assert _count_tokens("") == 0
    assert _count_tokens("abcd") == 1        # ceil(4/4) = 1
    assert _count_tokens("abcde") == 2       # ceil(5/4) = 2
    assert _count_tokens("a" * 400) == 100


def test_enforce_budget_no_truncation_needed():
    stack = ContextStack(
        l1_user_bio="short",
        l2_company="short",
        history=[{"role": "user", "content": "hi"}],
    )
    result = _enforce_budget(stack, context_window=100_000)
    assert result.l1_user_bio == "short"
    assert result.l2_company == "short"


def test_enforce_budget_zeroes_l9_first():
    """L9 should be zeroed first when over budget."""
    large = "x" * 10_000
    stack = ContextStack(
        l1_user_bio="bio",
        l9_agent_rag=large,
    )
    # Context window small enough to force truncation
    result = _enforce_budget(stack, context_window=100)
    assert result.l9_agent_rag == ""


def test_enforce_budget_history_trimmed_oldest_first():
    """History messages should be removed oldest first."""
    stack = ContextStack(
        history=[
            {"role": "user", "content": "a" * 4000},   # old
            {"role": "assistant", "content": "b" * 4000},
            {"role": "user", "content": "c" * 100},     # recent
        ],
    )
    result = _enforce_budget(stack, context_window=1000)
    # Recent message should survive
    contents = [m["content"] for m in result.history]
    assert any("c" * 100 in c for c in contents)
