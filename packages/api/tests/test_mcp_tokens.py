"""
Tests for KIN-325: MCP Token Management

Covers:
  - Token creation (TestMcpTokenCreate)
  - Token listing (TestMcpTokenList)
  - Token revocation (TestMcpTokenRevoke)

All Supabase calls are mocked. Uses client fixture from conftest.py.
Schema ref: docs/db-schema-spec.md §18 (mcp_tokens)
Token hashing: SHA-256 per ADR-006 §1
"""

import hashlib
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _make_token_row(
    name: str = "Claude Desktop",
    last_used_at=None,
    revoked_at=None,
) -> dict:
    return {
        "id": str(uuid4()),
        "user_id": TEST_USER_ID,
        "token_hash": _sha256("fake_raw_token"),
        "name": name,
        "last_used_at": last_used_at,
        "revoked_at": revoked_at,
        "created_at": "2026-03-23T10:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Task 1: Token creation
# ---------------------------------------------------------------------------


class TestMcpTokenCreate:
    """POST /api/v1/mcp/tokens — generate a new bearer token."""

    def test_create_token_returns_raw_token_once(self, client):
        row = _make_token_row()
        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[row]
            )

            resp = client.post("/api/v1/mcp/tokens", json={"name": "Claude Desktop"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == row["id"]
        assert data["name"] == "Claude Desktop"
        assert data["token"].startswith("mcp_")
        assert len(data["token"]) == 68  # "mcp_" (4) + 64 hex chars (32 bytes * 2)
        assert "created_at" in data
        # hash must NOT appear in the response
        assert "token_hash" not in data

    def test_create_token_stores_sha256_hash_not_plaintext(self, client):
        row = _make_token_row()
        captured_insert = {}

        def _capture_insert(data):
            captured_insert.update(data)
            mock_chain = MagicMock()
            mock_chain.execute.return_value = MagicMock(data=[row])
            return mock_chain

        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            mock_client.table.return_value.insert.side_effect = _capture_insert

            resp = client.post("/api/v1/mcp/tokens", json={"name": "Cursor"})

        assert resp.status_code == 200
        raw_token = resp.json()["token"][4:]  # strip "mcp_" prefix
        assert "token_hash" in captured_insert
        # stored hash must equal SHA-256 of the raw token
        assert captured_insert["token_hash"] == _sha256(raw_token)
        # stored hash must differ from the raw token
        assert captured_insert["token_hash"] != raw_token

    def test_create_token_name_required(self, client):
        resp = client.post("/api/v1/mcp/tokens", json={"name": ""})
        assert resp.status_code == 422

    def test_create_token_name_whitespace_only_rejected(self, client):
        resp = client.post("/api/v1/mcp/tokens", json={"name": "   "})
        assert resp.status_code == 422

    def test_create_token_name_max_64_chars(self, client):
        resp = client.post("/api/v1/mcp/tokens", json={"name": "x" * 65})
        assert resp.status_code == 422

    def test_create_token_name_64_chars_accepted(self, client):
        row = _make_token_row(name="x" * 64)
        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[row]
            )
            resp = client.post("/api/v1/mcp/tokens", json={"name": "x" * 64})
        assert resp.status_code == 200

    def test_create_token_name_whitespace_stripped(self, client):
        row = _make_token_row(name="Claude Desktop")
        captured_insert = {}

        def _capture_insert(data):
            captured_insert.update(data)
            mock_chain = MagicMock()
            mock_chain.execute.return_value = MagicMock(data=[row])
            return mock_chain

        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            mock_client.table.return_value.insert.side_effect = _capture_insert

            resp = client.post("/api/v1/mcp/tokens", json={"name": "  Claude Desktop  "})

        assert resp.status_code == 200
        assert captured_insert["name"] == "Claude Desktop"

    def test_create_token_requires_auth(self, raw_client):
        resp = raw_client.post("/api/v1/mcp/tokens", json={"name": "Test"})
        assert resp.status_code == 401

    def test_create_token_different_tokens_each_call(self, client):
        """Two successive creates must produce different tokens (os.urandom)."""
        row = _make_token_row()
        tokens = []

        def _make_mock():
            with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
                mock_client = MagicMock()
                mock_fn.return_value = mock_client
                mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
                    data=[row]
                )
                resp = client.post("/api/v1/mcp/tokens", json={"name": "Test"})
            return resp.json()["token"]

        t1, t2 = _make_mock(), _make_mock()
        assert t1 != t2


# ---------------------------------------------------------------------------
# Task 2: Token listing
# ---------------------------------------------------------------------------


class TestMcpTokenList:
    """GET /api/v1/mcp/tokens — list active tokens."""

    def test_list_tokens_returns_active_tokens(self, client):
        rows = [
            {
                "id": str(uuid4()),
                "name": "Claude Desktop",
                "last_used_at": None,
                "created_at": "2026-03-23T10:00:00+00:00",
            },
            {
                "id": str(uuid4()),
                "name": "Cursor",
                "last_used_at": "2026-03-23T12:00:00+00:00",
                "created_at": "2026-03-23T11:00:00+00:00",
            },
        ]
        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            (
                mock_client.table.return_value
                .select.return_value
                .eq.return_value
                .is_.return_value
                .order.return_value
                .execute.return_value
            ) = MagicMock(data=rows)

            resp = client.get("/api/v1/mcp/tokens")

        assert resp.status_code == 200
        data = resp.json()
        assert "tokens" in data
        assert len(data["tokens"]) == 2
        assert data["tokens"][0]["name"] == "Claude Desktop"
        assert data["tokens"][1]["name"] == "Cursor"

    def test_list_tokens_excludes_token_hash(self, client):
        rows = [{"id": str(uuid4()), "name": "Test", "last_used_at": None, "created_at": "2026-03-23T10:00:00+00:00"}]
        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            (
                mock_client.table.return_value
                .select.return_value
                .eq.return_value
                .is_.return_value
                .order.return_value
                .execute.return_value
            ) = MagicMock(data=rows)

            resp = client.get("/api/v1/mcp/tokens")

        assert resp.status_code == 200
        for token in resp.json()["tokens"]:
            assert "token_hash" not in token
            assert "token" not in token

    def test_list_tokens_last_used_at_null_for_unused(self, client):
        rows = [{"id": str(uuid4()), "name": "Test", "last_used_at": None, "created_at": "2026-03-23T10:00:00+00:00"}]
        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            (
                mock_client.table.return_value
                .select.return_value
                .eq.return_value
                .is_.return_value
                .order.return_value
                .execute.return_value
            ) = MagicMock(data=rows)

            resp = client.get("/api/v1/mcp/tokens")

        assert resp.status_code == 200
        assert resp.json()["tokens"][0]["last_used_at"] is None

    def test_list_tokens_empty_when_none(self, client):
        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            (
                mock_client.table.return_value
                .select.return_value
                .eq.return_value
                .is_.return_value
                .order.return_value
                .execute.return_value
            ) = MagicMock(data=[])

            resp = client.get("/api/v1/mcp/tokens")

        assert resp.status_code == 200
        assert resp.json()["tokens"] == []

    def test_list_tokens_requires_auth(self, raw_client):
        resp = raw_client.get("/api/v1/mcp/tokens")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Task 3: Token revocation
# ---------------------------------------------------------------------------


class TestMcpTokenRevoke:
    """PATCH /api/v1/mcp/tokens/{id}/revoke — revoke a token."""

    def _setup_revoke_mock(self, mock_client, fetch_data, update_data=None):
        """Wire fetch (single) and update mocks on mock_client."""
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=fetch_data
        )
        if update_data is not None:
            mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=update_data
            )

    def test_revoke_token_success(self, client):
        token_id = str(uuid4())
        fetch_row = {"id": token_id, "revoked_at": None}
        update_row = {"id": token_id, "revoked_at": "2026-03-23T15:00:00+00:00"}

        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            self._setup_revoke_mock(mock_client, fetch_row, [update_row])

            resp = client.patch(f"/api/v1/mcp/tokens/{token_id}/revoke")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == token_id
        assert data["revoked_at"] == "2026-03-23T15:00:00+00:00"

    def test_revoke_token_not_found(self, client):
        token_id = str(uuid4())
        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            self._setup_revoke_mock(mock_client, None)

            resp = client.patch(f"/api/v1/mcp/tokens/{token_id}/revoke")

        assert resp.status_code == 404

    def test_revoke_token_already_revoked_returns_409(self, client):
        token_id = str(uuid4())
        fetch_row = {"id": token_id, "revoked_at": "2026-03-22T10:00:00+00:00"}

        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            self._setup_revoke_mock(mock_client, fetch_row)

            resp = client.patch(f"/api/v1/mcp/tokens/{token_id}/revoke")

        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    def test_revoke_token_scoped_to_current_user(self, client):
        """The fetch query must include user_id filter — different user's token returns 404."""
        token_id = str(uuid4())
        # Simulates: token exists but belongs to another user → Supabase returns empty
        with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
            mock_client = MagicMock()
            mock_fn.return_value = mock_client
            self._setup_revoke_mock(mock_client, None)

            resp = client.patch(f"/api/v1/mcp/tokens/{token_id}/revoke")

        assert resp.status_code == 404

    def test_revoke_token_requires_auth(self, raw_client):
        resp = raw_client.patch(f"/api/v1/mcp/tokens/{uuid4()}/revoke")
        assert resp.status_code == 401
