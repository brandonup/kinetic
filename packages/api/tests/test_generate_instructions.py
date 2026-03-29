"""
Tests for KIN-366: POST /api/v1/agents/:id/generate-instructions.

Generates a system prompt from an agent's existing KB documents using the user's BYOK key.
All Supabase and LLM calls are mocked. Uses client fixture from conftest.py.

Spec: docs/specs/agents.md §7, §10
Schema ref: docs/db-schema-spec.md §8, §10, §12, §13
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_AGENT_ID = str(uuid4())
TEST_KB_ID = str(uuid4())
OTHER_USER_ID = str(uuid4())

PATCH_SUPABASE = "app.api.routes.agents.get_supabase_client"
PATCH_LLM = "app.services.llm_client.call_llm"
PATCH_DECRYPT = "app.services.encryption.decrypt_api_key"
PATCH_MASTER_KEY = "app.services.encryption.load_master_key"

ENDPOINT = f"/api/v1/agents/{TEST_AGENT_ID}/generate-instructions"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_row(owner_id: str = TEST_USER_ID, agent_type: str = "thought_leader") -> dict:
    return {
        "id": TEST_AGENT_ID,
        "owner_id": owner_id,
        "name": "Nate Jones",
        "instructions": "Existing instructions",
        "type": agent_type,
        "visibility": "private",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _kb_rows(kb_id: str = TEST_KB_ID) -> list[dict]:
    return [{"id": kb_id}]


def _doc_rows(count: int = 2) -> list[dict]:
    return [
        {"id": str(uuid4()), "title": f"Document {i}", "status": "completed", "deleted_at": None}
        for i in range(count)
    ]


def _chunk_rows() -> list[dict]:
    return [
        {"text": "This is some corpus content about strategy and leadership.", "chunk_index": 0},
        {"text": "More content about decision-making frameworks.", "chunk_index": 1},
    ]


def _api_key_row() -> dict:
    return {"provider": "openai", "key_ciphertext": "aabbcc", "key_nonce": "112233"}


def _make_table_router(chains: dict[str, MagicMock]) -> MagicMock:
    """Build a table() side_effect that routes by table name."""
    def router(name):
        return chains.get(name, MagicMock())
    return MagicMock(side_effect=router)


def _agent_chain(owner_id: str = TEST_USER_ID) -> MagicMock:
    chain = MagicMock()
    chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data=_agent_row(owner_id=owner_id)
    )
    return chain


def _kb_chain(rows: list[dict] | None = None) -> MagicMock:
    chain = MagicMock()
    chain.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=rows if rows is not None else _kb_rows()
    )
    return chain


def _docs_chain(rows: list[dict] | None = None) -> MagicMock:
    chain = MagicMock()
    chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
        data=rows if rows is not None else _doc_rows()
    )
    return chain


def _chunks_chain(rows: list[dict] | None = None) -> MagicMock:
    chain = MagicMock()
    chain.select.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(
        data=rows if rows is not None else _chunk_rows()
    )
    return chain


def _keys_chain(rows: list[dict] | None = None) -> MagicMock:
    chain = MagicMock()
    chain.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=rows if rows is not None else [_api_key_row()]
    )
    return chain


def _full_chains(**overrides) -> dict[str, MagicMock]:
    """Return the standard chain set for a happy-path test. Override individual chains."""
    defaults = {
        "agent_definitions": _agent_chain(),
        "knowledge_bases": _kb_chain(),
        "knowledge_base_documents": _docs_chain(),
        "knowledge_base_chunks": _chunks_chain(),
        "user_api_keys": _keys_chain(),
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateInstructionsOwnerAuth:
    def test_non_owner_gets_403(self, client):
        """Non-owner calling generate-instructions → 403."""
        with patch(PATCH_SUPABASE) as mock_db:
            mock_db.return_value.table = _make_table_router({
                "agent_definitions": _agent_chain(owner_id=OTHER_USER_ID),
            })
            resp = client.post(ENDPOINT)
        assert resp.status_code == 403


class TestGenerateInstructionsGating:
    def test_no_kb_returns_400(self, client):
        """Agent with no knowledge base → 400."""
        with patch(PATCH_SUPABASE) as mock_db:
            mock_db.return_value.table = _make_table_router({
                "agent_definitions": _agent_chain(),
                "knowledge_bases": _kb_chain(rows=[]),  # no KB
            })
            resp = client.post(ENDPOINT)
        assert resp.status_code == 400
        body = resp.json()
        msg = body.get("detail", "") or body.get("error", {}).get("message", "")
        assert "knowledge base" in msg.lower()

    def test_no_docs_returns_400(self, client):
        """Agent has KB but no completed documents → 400."""
        with patch(PATCH_SUPABASE) as mock_db:
            mock_db.return_value.table = _make_table_router({
                "agent_definitions": _agent_chain(),
                "knowledge_bases": _kb_chain(),
                "knowledge_base_documents": _docs_chain(rows=[]),  # no docs
            })
            resp = client.post(ENDPOINT)
        assert resp.status_code == 400
        body = resp.json()
        msg = body.get("detail", "") or body.get("error", {}).get("message", "")
        assert "document" in msg.lower()

    def test_no_api_key_returns_400(self, client):
        """User has no BYOK key configured → 400."""
        with patch(PATCH_SUPABASE) as mock_db:
            mock_db.return_value.table = _make_table_router(
                _full_chains(user_api_keys=_keys_chain(rows=[]))
            )
            resp = client.post(ENDPOINT)
        assert resp.status_code == 400
        body = resp.json()
        msg = body.get("detail", "") or body.get("error", {}).get("message", "")
        assert "api key" in msg.lower()


class TestGenerateInstructionsSuccess:
    def test_owner_can_generate_instructions(self, client):
        """Full happy path: returns generated instructions text."""
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM, return_value="You are Nate Jones, a strategic operator...") as mock_llm,
            patch(PATCH_DECRYPT, return_value="sk-test-key"),
            patch(PATCH_MASTER_KEY, return_value=b"masterkey"),
        ):
            mock_db.return_value.table = _make_table_router(_full_chains())
            resp = client.post(ENDPOINT)

        assert resp.status_code == 200
        body = resp.json()
        assert body["instructions"] == "You are Nate Jones, a strategic operator..."
        mock_llm.assert_called_once()


class TestGenerateInstructionsLLMFailure:
    def test_llm_failure_returns_500(self, client):
        """LLM raises RuntimeError → endpoint returns 500."""
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM, side_effect=RuntimeError("LLM unavailable")),
            patch(PATCH_DECRYPT, return_value="sk-test-key"),
            patch(PATCH_MASTER_KEY, return_value=b"masterkey"),
        ):
            mock_db.return_value.table = _make_table_router(_full_chains())
            resp = client.post(ENDPOINT)

        assert resp.status_code == 500
        assert "detail" in resp.json()
