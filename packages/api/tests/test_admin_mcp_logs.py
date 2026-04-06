"""
Tests for KIN-452: Admin MCP activity logs

Covers:
  - List MCP logs (TestListMcpLogs) — admin only, paginated
  - MCP stats (TestMcpLogStats) — admin only, aggregated by agent

All Supabase calls are mocked. Uses admin_client + client fixtures from conftest.py.
Schema ref: docs/db-schema-spec.md (messages_mcp)
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

TEST_USER_ID = str(uuid4())
TEST_AGENT_DEF_ID = str(uuid4())
TEST_AGENT_INST_ID = str(uuid4())
PATCH_TARGET = "app.api.routes.admin_mcp_logs.get_supabase_client"


def _log_row(
    user_id: str = TEST_USER_ID,
    agent_slug: str = "nate",
    query: str = "What is product-market fit?",
    latency_ms: int = 350,
    embedding_latency_ms: int = 120,
) -> dict:
    return {
        "id": str(uuid4()),
        "user_id": user_id,
        "agent_definition_id": TEST_AGENT_DEF_ID,
        "agent_instance_id": TEST_AGENT_INST_ID,
        "query": query,
        "agent_slug": agent_slug,
        "context_payload": "## Persona\n\nNate...",
        "layer_status": {"persona": "ok", "memory": "ok", "framework": "empty", "kb": "ok"},
        "latency_ms": latency_ms,
        "embedding_latency_ms": embedding_latency_ms,
        "error": None,
        "mcp_session_id": "sess-abc",
        "created_at": "2026-04-05T12:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# List MCP logs — admin only
# ---------------------------------------------------------------------------


class TestListMcpLogs:
    def test_returns_logs_for_user(self, admin_client):
        row = _log_row()
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .eq.return_value
            .order.return_value
            .limit.return_value
            .execute.return_value
        ) = MagicMock(data=[row])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.get(
                f"/api/v1/admin/mcp/logs?user_id={TEST_USER_ID}"
            )
        assert response.status_code == 200
        body = response.json()
        assert "logs" in body
        assert len(body["logs"]) == 1
        assert body["logs"][0]["agent_slug"] == "nate"
        assert body["logs"][0]["latency_ms"] == 350

    def test_returns_all_logs_without_user_filter(self, admin_client):
        rows = [_log_row(), _log_row(agent_slug="monica")]
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .order.return_value
            .limit.return_value
            .execute.return_value
        ) = MagicMock(data=rows)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.get("/api/v1/admin/mcp/logs")
        assert response.status_code == 200
        assert len(response.json()["logs"]) == 2

    def test_returns_empty(self, admin_client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .order.return_value
            .limit.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.get("/api/v1/admin/mcp/logs")
        assert response.status_code == 200
        assert response.json() == {"logs": []}

    def test_non_admin_returns_403(self, client):
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app

        async def _raise_auth_error() -> None:
            raise AuthorizationError()

        app.dependency_overrides[require_admin] = _raise_auth_error
        try:
            response = client.get("/api/v1/admin/mcp/logs")
        finally:
            del app.dependency_overrides[require_admin]
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# MCP stats — admin only
# ---------------------------------------------------------------------------


class TestMcpLogStats:
    def test_returns_aggregated_stats(self, admin_client):
        rows = [
            _log_row(agent_slug="nate", latency_ms=300, embedding_latency_ms=100),
            _log_row(agent_slug="nate", latency_ms=400, embedding_latency_ms=140),
            _log_row(agent_slug="monica", latency_ms=200, embedding_latency_ms=80),
        ]
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .gte.return_value
            .execute.return_value
        ) = MagicMock(data=rows)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.get("/api/v1/admin/mcp/stats?days=7")
        assert response.status_code == 200
        body = response.json()
        assert "stats" in body
        assert len(body["stats"]) == 2
        # Find nate stats
        nate = next(s for s in body["stats"] if s["agent_slug"] == "nate")
        assert nate["invocations"] == 2
        assert nate["avg_latency_ms"] == 350.0
        assert nate["avg_embedding_latency_ms"] == 120.0
        # Find monica stats
        monica = next(s for s in body["stats"] if s["agent_slug"] == "monica")
        assert monica["invocations"] == 1

    def test_returns_empty_stats(self, admin_client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .gte.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.get("/api/v1/admin/mcp/stats")
        assert response.status_code == 200
        assert response.json() == {"stats": []}

    def test_non_admin_returns_403(self, client):
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app

        async def _raise_auth_error() -> None:
            raise AuthorizationError()

        app.dependency_overrides[require_admin] = _raise_auth_error
        try:
            response = client.get("/api/v1/admin/mcp/stats")
        finally:
            del app.dependency_overrides[require_admin]
        assert response.status_code == 403
