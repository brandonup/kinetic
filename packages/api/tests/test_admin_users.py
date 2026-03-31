"""
Tests for KIN-264: Admin Users tab

Covers:
  - List users (TestListUsers) — admin only
  - Disable user (TestDisableUser) — admin only; 409 when public agents exist
  - Enable user (TestEnableUser) — admin only; 404 if not found
  - Transfer agent (TestTransferAgent) — admin only; 404 if not found

All Supabase calls are mocked. Uses client + admin_client fixtures from conftest.py.
Schema ref: docs/db-schema-spec.md §1 (users), §8 (agent_definitions)
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

TEST_USER_ID = str(uuid4())
PATCH_TARGET = "app.api.routes.admin_users.get_supabase_client"


def _user_row(
    user_id: str = TEST_USER_ID,
    name: str = "Alice",
    email: str = "alice@example.com",
    role: str = "user",
    disabled_at=None,
) -> dict:
    return {
        "id": user_id,
        "name": name,
        "email": email,
        "role": role,
        "disabled_at": disabled_at,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# List users — admin only
# ---------------------------------------------------------------------------


class TestListUsers:
    def test_list_returns_users_with_email(self, admin_client):
        row = _user_row()
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .order.return_value
            .execute.return_value
        ) = MagicMock(data=[row])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.get("/api/v1/admin/users")
        assert response.status_code == 200
        users = response.json()["users"]
        assert len(users) == 1
        assert users[0]["email"] == "alice@example.com"
        assert users[0]["name"] == "Alice"

    def test_list_returns_empty(self, admin_client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .order.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.get("/api/v1/admin/users")
        assert response.status_code == 200
        assert response.json() == {"users": []}

    def test_list_non_admin_returns_403(self, client):
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app

        async def _raise_auth_error() -> None:
            raise AuthorizationError()

        app.dependency_overrides[require_admin] = _raise_auth_error
        try:
            response = client.get("/api/v1/admin/users")
        finally:
            del app.dependency_overrides[require_admin]
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Disable user — admin only
# ---------------------------------------------------------------------------


class TestDisableUser:
    def test_disable_returns_204(self, admin_client):
        mock_db = MagicMock()
        # No public agents
        (
            mock_db.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        # Update succeeds
        (
            mock_db.table.return_value
            .update.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[_user_row()])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(f"/api/v1/admin/users/{TEST_USER_ID}/disable")
        assert response.status_code == 204

    def test_disable_409_when_public_agents_exist(self, admin_client):
        agent_id = str(uuid4())
        mock_db = MagicMock()
        # Public agents found
        (
            mock_db.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[{"id": agent_id}])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(f"/api/v1/admin/users/{TEST_USER_ID}/disable")
        assert response.status_code == 409
        body = response.json()
        assert body["detail"]["error"] == "transfer_required"
        assert agent_id in body["detail"]["public_agent_ids"]

    def test_disable_non_admin_returns_403(self, client):
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app

        async def _raise_auth_error() -> None:
            raise AuthorizationError()

        app.dependency_overrides[require_admin] = _raise_auth_error
        try:
            response = client.patch(f"/api/v1/admin/users/{TEST_USER_ID}/disable")
        finally:
            del app.dependency_overrides[require_admin]
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Enable user — admin only
# ---------------------------------------------------------------------------


class TestEnableUser:
    def test_enable_returns_200(self, admin_client):
        row = _user_row(disabled_at="2026-01-01T00:00:00+00:00")
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .update.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[row])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(f"/api/v1/admin/users/{TEST_USER_ID}/enable")
        assert response.status_code == 200
        assert response.json()["id"] == TEST_USER_ID

    def test_enable_not_found_returns_404(self, admin_client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .update.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(f"/api/v1/admin/users/{TEST_USER_ID}/enable")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Transfer agent — admin only
# ---------------------------------------------------------------------------


class TestTransferAgent:
    def test_transfer_returns_200(self, admin_client):
        new_owner_id = str(uuid4())
        agent_id = str(uuid4())
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .update.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[{"id": agent_id, "owner_id": new_owner_id}])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(
                f"/api/v1/admin/users/{TEST_USER_ID}/transfer-agent",
                json={"agent_id": agent_id, "new_owner_id": new_owner_id},
            )
        assert response.status_code == 200
        assert response.json()["owner_id"] == new_owner_id

    def test_transfer_not_found_returns_404(self, admin_client):
        new_owner_id = str(uuid4())
        agent_id = str(uuid4())
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .update.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(
                f"/api/v1/admin/users/{TEST_USER_ID}/transfer-agent",
                json={"agent_id": agent_id, "new_owner_id": new_owner_id},
            )
        assert response.status_code == 404

    def test_transfer_missing_fields_returns_422(self, admin_client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            response = admin_client.patch(
                f"/api/v1/admin/users/{TEST_USER_ID}/transfer-agent",
                json={"agent_id": str(uuid4())},  # missing new_owner_id
            )
        assert response.status_code == 422

    def test_transfer_non_admin_returns_403(self, client):
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app

        async def _raise_auth_error() -> None:
            raise AuthorizationError()

        app.dependency_overrides[require_admin] = _raise_auth_error
        try:
            response = client.patch(
                f"/api/v1/admin/users/{TEST_USER_ID}/transfer-agent",
                json={"agent_id": str(uuid4()), "new_owner_id": str(uuid4())},
            )
        finally:
            del app.dependency_overrides[require_admin]
        assert response.status_code == 403
