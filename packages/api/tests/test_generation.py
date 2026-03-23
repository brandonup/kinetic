"""
Integration tests for the generation endpoint — KIN-279.

POST /api/v1/conversations/{id}/messages

Tests cover:
  - 200 with SSE stream for valid request
  - 404 for missing / soft-deleted conversation
  - 422 for empty message content
  - 402 for missing BYOK key
  - Model resolution: request model → user default → 422 if neither

Spec ref: docs/specs/kin-257-projects-conversations-spec.md §2.3
KIN-276: implementation ticket
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

CONV_ID = str(uuid4())
USER_ID = "00000000-0000-0000-0000-000000000001"  # matches conftest TEST_USER_ID
MODEL_ID = str(uuid4())
COMPANY_ID = str(uuid4())

_CONV_ROW = {
    "id": CONV_ID,
    "company_id": COMPANY_ID,
    "project_id": None,
    "active_agent_id": None,
    "title": None,
    "user_id": USER_ID,
}

_MODEL_ROW = {
    "id": MODEL_ID,
    "provider": "anthropic",
    "model_id": "claude-haiku-4-5-20251001",
    "context_window": 200000,
    "display_name": "Claude Haiku 4.5",
}

PATCH_DB = "app.api.routes.generation.get_supabase_client"
PATCH_CS = "app.api.routes.generation.context_stack_service.assemble"
PATCH_LITELLM = "app.api.routes.generation.litellm"
PATCH_DECRYPT = "app.api.routes.generation.decrypt"


def _mock_chain(return_data, *, count: int = 0):
    result = MagicMock()
    result.data = return_data
    result.count = count
    chain = MagicMock()
    for method in (
        "select", "eq", "neq", "is_", "order", "limit",
        "maybe_single", "insert", "update", "delete",
    ):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = result
    return chain, result


def _make_supabase(conv_found: bool = True, model_found: bool = True, has_key: bool = True):
    sb = MagicMock()
    call_counts: dict[str, int] = {}

    def _table(name: str):
        call_counts[name] = call_counts.get(name, 0) + 1
        if name == "conversations":
            data = _CONV_ROW if conv_found else None
            chain, _ = _mock_chain(data)
        elif name == "llm_models":
            data = _MODEL_ROW if model_found else None
            chain, _ = _mock_chain(data)
        elif name == "users":
            # default_model_id
            chain, _ = _mock_chain({"default_model_id": MODEL_ID})
        elif name == "user_api_keys":
            data = (
                {"key_ciphertext": "Y2lwaGVy", "key_nonce": "bm9uY2U="}
                if has_key
                else None
            )
            chain, _ = _mock_chain(data)
        elif name == "messages":
            # sequence query returns empty (next_seq=0) then insert ok
            chain, r = _mock_chain([])
            # insert returns a row
            insert_chain, _ = _mock_chain([{"id": str(uuid4())}])
            insert_chain.execute.return_value = MagicMock(data=[{"id": str(uuid4())}])
            chain.insert.return_value = insert_chain
            chain.count = 0
            r.count = 0
        elif name == "conversation_summaries":
            chain, _ = _mock_chain([])
        elif name == "knowledge_bases":
            chain, _ = _mock_chain(None)
        else:
            chain, _ = _mock_chain(None)
        return chain

    sb.table.side_effect = _table
    return sb


def _fake_context():
    from app.services.context_stack import ContextStack
    return ContextStack(system_prompt="You are helpful.", history=[])


def _fake_stream():
    """Async iterator that yields two content deltas."""
    class _Chunk:
        def __init__(self, content):
            self.choices = [MagicMock(delta=MagicMock(content=content))]

    async def _gen():
        yield _Chunk("Hello ")
        yield _Chunk("world!")

    return _gen()


class TestSendMessage:
    def test_404_when_conversation_not_found(self, client):
        sb = _make_supabase(conv_found=False)
        with patch(PATCH_DB, return_value=sb):
            res = client.post(
                f"/api/v1/conversations/{CONV_ID}/messages",
                json={"content": "Hi"},
            )
        assert res.status_code == 404

    def test_422_for_empty_content(self, client):
        with patch(PATCH_DB, return_value=_make_supabase()):
            res = client.post(
                f"/api/v1/conversations/{CONV_ID}/messages",
                json={"content": "   "},
            )
        assert res.status_code == 422

    def test_422_for_missing_content_field(self, client):
        with patch(PATCH_DB, return_value=_make_supabase()):
            res = client.post(
                f"/api/v1/conversations/{CONV_ID}/messages",
                json={},
            )
        assert res.status_code == 422

    def test_402_when_no_byok_key(self, client):
        sb = _make_supabase(has_key=False)
        with patch(PATCH_DB, return_value=sb):
            res = client.post(
                f"/api/v1/conversations/{CONV_ID}/messages",
                json={"content": "Hello"},
            )
        assert res.status_code == 402

    def test_422_when_model_not_found(self, client):
        sb = _make_supabase(model_found=False)
        # Also make user have no default model
        def _table(name):
            if name == "conversations":
                chain, _ = _mock_chain(_CONV_ROW)
            elif name == "users":
                chain, _ = _mock_chain({"default_model_id": None})
            elif name == "llm_models":
                chain, _ = _mock_chain(None)
            else:
                chain, _ = _mock_chain(None)
            return chain

        sb2 = MagicMock()
        sb2.table.side_effect = _table

        with patch(PATCH_DB, return_value=sb2):
            res = client.post(
                f"/api/v1/conversations/{CONV_ID}/messages",
                json={"content": "Hello"},
            )
        assert res.status_code == 422

    def test_200_sse_stream_for_valid_request(self, client):
        sb = _make_supabase()

        with (
            patch(PATCH_DB, return_value=sb),
            patch(PATCH_DECRYPT, return_value="sk-test-key"),
            patch(PATCH_CS, return_value=_fake_context()),
            patch(PATCH_LITELLM) as mock_litellm,
        ):
            mock_litellm.acompletion = AsyncMock(return_value=_fake_stream())

            res = client.post(
                f"/api/v1/conversations/{CONV_ID}/messages",
                json={"content": "Hello!"},
            )

        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")

    def test_sse_stream_contains_done_event(self, client):
        sb = _make_supabase()

        with (
            patch(PATCH_DB, return_value=sb),
            patch(PATCH_DECRYPT, return_value="sk-test-key"),
            patch(PATCH_CS, return_value=_fake_context()),
            patch(PATCH_LITELLM) as mock_litellm,
        ):
            mock_litellm.acompletion = AsyncMock(return_value=_fake_stream())

            res = client.post(
                f"/api/v1/conversations/{CONV_ID}/messages",
                json={"content": "Hello!"},
            )

        # Parse SSE events
        events = [
            line[6:] for line in res.text.splitlines()
            if line.startswith("data: ")
        ]
        parsed = [json.loads(e) for e in events if e]

        assert any(e.get("done") for e in parsed), "Expected 'done' event in stream"

    def test_sse_stream_contains_delta_events(self, client):
        sb = _make_supabase()

        with (
            patch(PATCH_DB, return_value=sb),
            patch(PATCH_DECRYPT, return_value="sk-test-key"),
            patch(PATCH_CS, return_value=_fake_context()),
            patch(PATCH_LITELLM) as mock_litellm,
        ):
            mock_litellm.acompletion = AsyncMock(return_value=_fake_stream())

            res = client.post(
                f"/api/v1/conversations/{CONV_ID}/messages",
                json={"content": "Hello!"},
            )

        events = [
            line[6:] for line in res.text.splitlines()
            if line.startswith("data: ")
        ]
        parsed = [json.loads(e) for e in events if e]
        delta_events = [e for e in parsed if "delta" in e]

        assert len(delta_events) >= 1
        combined = "".join(e["delta"] for e in delta_events)
        assert "Hello" in combined or "world" in combined
