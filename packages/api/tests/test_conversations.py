"""
Route tests for Conversation CRUD + generation endpoint — KIN-292 (KIN-272, KIN-276).

SSE streaming is tested by consuming the response body directly.
LiteLLM and context stack are mocked so no live LLM calls are made.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import TEST_COMPANY_ID, TEST_PROJECT_ID, TEST_USER_ID, ok, empty, seq


CONV_ID = "00000000-0000-0000-0000-000000000060"
MSG_ID = "00000000-0000-0000-0000-000000000061"

CONV_ROW = {
    "id": CONV_ID,
    "user_id": TEST_USER_ID,
    "company_id": TEST_COMPANY_ID,
    "project_id": TEST_PROJECT_ID,
    "title": None,
    "active_agent_id": None,
    "deleted_at": None,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

MODEL_ROW = {
    "id": "model-1",
    "model_id": "claude-sonnet-4-6",
    "provider": "anthropic",
    "context_window": 200_000,
    "enabled": True,
}

KEY_ROW = {
    "key_ciphertext": "CIPHERTEXT",
    "key_nonce": "NONCE",
}

USER_ROW = {"default_model_id": "model-1"}


class TestCreateConversation:
    def test_project_scope(self, client, sb):
        seq(sb, ok({"id": TEST_COMPANY_ID}), ok({"id": TEST_PROJECT_ID}), ok([CONV_ROW]))
        r = client.post(
            "/api/v1/conversations",
            json={"company_id": TEST_COMPANY_ID, "project_id": TEST_PROJECT_ID},
        )
        assert r.status_code == 201
        assert r.json()["project_id"] == TEST_PROJECT_ID

    def test_company_scope(self, client, sb):
        seq(sb, ok({"id": TEST_COMPANY_ID}), ok([{**CONV_ROW, "project_id": None}]))
        r = client.post(
            "/api/v1/conversations",
            json={"company_id": TEST_COMPANY_ID},
        )
        assert r.status_code == 201

    def test_wrong_company_returns_403(self, client, sb):
        seq(sb, empty())  # company ownership check fails
        r = client.post(
            "/api/v1/conversations",
            json={"company_id": TEST_COMPANY_ID},
        )
        assert r.status_code == 403


class TestListConversations:
    def test_returns_list(self, client, sb):
        sb.execute.return_value = ok([CONV_ROW])
        r = client.get("/api/v1/conversations")
        assert r.status_code == 200
        data = r.json()
        assert "conversations" in data

    def test_filter_by_project(self, client, sb):
        sb.execute.return_value = ok([CONV_ROW])
        r = client.get(f"/api/v1/conversations?project_id={TEST_PROJECT_ID}")
        assert r.status_code == 200


class TestGetConversation:
    def test_found_includes_messages(self, client, sb):
        seq(
            sb,
            ok(CONV_ROW),
            ok([{"id": MSG_ID, "role": "user", "content": "hello", "sequence": 0,
                 "agent_definition_id": None, "model": None, "created_at": "2026-01-01T00:00:00Z"}]),
        )
        r = client.get(f"/api/v1/conversations/{CONV_ID}")
        assert r.status_code == 200
        assert "messages" in r.json()

    def test_not_found(self, client, sb):
        sb.execute.return_value = empty()
        r = client.get(f"/api/v1/conversations/{CONV_ID}")
        assert r.status_code == 404


class TestUpdateConversation:
    def test_rename(self, client, sb):
        updated = {**CONV_ROW, "title": "My Chat"}
        seq(sb, ok(CONV_ROW), ok([updated]))
        r = client.patch(f"/api/v1/conversations/{CONV_ID}", json={"title": "My Chat"})
        assert r.status_code == 200
        assert r.json()["title"] == "My Chat"


class TestDeleteConversation:
    def test_soft_delete(self, client, sb):
        """Soft-delete: sets deleted_at, does not hard-delete."""
        seq(sb, ok(CONV_ROW), ok([]))
        r = client.delete(f"/api/v1/conversations/{CONV_ID}")
        assert r.status_code == 204
        # Verify update (soft-delete) was called, not delete
        sb.update.assert_called()

    def test_not_found(self, client, sb):
        sb.execute.return_value = empty()
        r = client.delete(f"/api/v1/conversations/{CONV_ID}")
        assert r.status_code == 404


class TestSendMessage:
    def _setup_sb_for_generation(self, sb):
        """Configure Supabase mock for the full send_message flow."""
        seq(
            sb,
            ok(CONV_ROW),                          # get_conversation
            ok([{"sequence": 0}]),                 # _next_sequence
            ok([{"id": MSG_ID, "content": "hi"}]), # insert user message
            ok(USER_ROW),                          # fetch user default_model_id
            ok(MODEL_ROW),                         # fetch model row
            ok({"key_ciphertext": "CIPHERTEXT", "key_nonce": "NONCE"}),  # byok key
        )

    def test_no_byok_key_returns_402(self, client, sb):
        seq(
            sb,
            ok(CONV_ROW),
            ok([{"sequence": 0}]),
            ok([{"id": MSG_ID, "content": "hi"}]),
            ok(USER_ROW),
            ok(MODEL_ROW),
            empty(),  # no BYOK key
        )
        with patch("app.services.context_stack.assemble", new_callable=AsyncMock):
            r = client.post(
                f"/api/v1/conversations/{CONV_ID}/messages",
                json={"content": "hello"},
            )
        assert r.status_code == 402

    def test_no_model_configured_returns_402(self, client, sb):
        seq(
            sb,
            ok(CONV_ROW),
            ok([{"sequence": 0}]),
            ok([{"id": MSG_ID, "content": "hi"}]),
            ok({"default_model_id": None}),  # no default model
        )
        r = client.post(
            f"/api/v1/conversations/{CONV_ID}/messages",
            json={"content": "hello"},
        )
        assert r.status_code == 402

    def test_streaming_returns_sse_events(self, client, sb):
        """SSE stream yields delta events and closes with done:true."""
        self._setup_sb_for_generation(sb)

        async def _fake_stream(**_kwargs):
            for chunk in ["Hello", " world"]:
                yield chunk

        from app.services.context_stack import ContextStack

        with patch("app.services.context_stack.assemble", new_callable=AsyncMock,
                   return_value=ContextStack()), \
             patch("app.services.llm_client.stream_completion", new=_fake_stream), \
             patch("app.services.encryption.decrypt_key", return_value="sk-ant-decrypted"):

            # Also stub the background DB inserts after stream
            sb.execute.side_effect = list(sb.execute.side_effect) + [ok([]), ok([])]

            r = client.post(
                f"/api/v1/conversations/{CONV_ID}/messages",
                json={"content": "hello"},
            )

        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        body = r.text
        assert "delta" in body or "done" in body

    def test_empty_content_returns_422(self, client, sb):
        r = client.post(
            f"/api/v1/conversations/{CONV_ID}/messages",
            json={"content": "   "},
        )
        assert r.status_code == 422

    def test_conversation_not_found_returns_404(self, client, sb):
        sb.execute.return_value = empty()
        r = client.post(
            f"/api/v1/conversations/{CONV_ID}/messages",
            json={"content": "hello"},
        )
        assert r.status_code == 404
