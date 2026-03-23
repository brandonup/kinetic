"""
Tests for Admin Users tab — KIN-264 / KIN-278.

Covers:
  - GET    /api/v1/admin/users          (admin only)
  - PATCH  /api/v1/admin/users/{id}/disable
  - PATCH  /api/v1/admin/users/{id}/enable
  - PATCH  /api/v1/admin/users/{id}/transfer-agent
  - 403 enforcement for non-admin callers
  - 409 disable gate when user owns public agents
"""

import pytest
from .conftest import REGULAR_USER_ID, OTHER_USER_ID


# ---------------------------------------------------------------------------
# GET /api/v1/admin/users
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_admin_can_list_all_users(self, admin_client):
        resp = admin_client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_response_includes_required_fields(self, admin_client):
        resp = admin_client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        if resp.json():
            user = resp.json()[0]
            for field in ("id", "email", "name", "role", "created_at"):
                assert field in user, f"Missing field: {field}"
            # disabled_at may be None but must be present
            assert "disabled_at" in user

    def test_non_admin_returns_403(self, auth_client):
        resp = auth_client.get("/api/v1/admin/users")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/admin/users/{id}/disable
# ---------------------------------------------------------------------------

class TestDisableUser:
    def test_disable_user_with_no_public_agents_succeeds(self, admin_client):
        resp = admin_client.patch(f"/api/v1/admin/users/{OTHER_USER_ID}/disable")
        assert resp.status_code == 200
        # disabled_at should now be set
        data = resp.json()
        assert data.get("disabled_at") is not None

    def test_disable_blocked_when_user_has_public_agents(self, admin_client, other_client):
        # Create a public agent owned by OTHER_USER
        agent_resp = other_client.post(
            "/api/v1/agents",
            json={
                "name": "Public Agent",
                "system_prompt": "You are helpful.",
                "visibility": "public",
            },
        )
        if agent_resp.status_code not in (200, 201):
            pytest.skip("Agent endpoint not yet implemented (Sprint 4)")

        agent_id = agent_resp.json()["id"]

        # Attempt to disable OTHER_USER — should be blocked
        resp = admin_client.patch(f"/api/v1/admin/users/{OTHER_USER_ID}/disable")
        assert resp.status_code == 409
        body = resp.json()
        assert body.get("error") == "transfer_required"
        assert agent_id in body.get("public_agent_ids", [])

    def test_disable_succeeds_after_agent_set_private(self, admin_client, other_client):
        agent_resp = other_client.post(
            "/api/v1/agents",
            json={
                "name": "Was Public",
                "system_prompt": "You are helpful.",
                "visibility": "public",
            },
        )
        if agent_resp.status_code not in (200, 201):
            pytest.skip("Agent endpoint not yet implemented (Sprint 4)")

        agent_id = agent_resp.json()["id"]

        # First disable attempt blocked
        resp = admin_client.patch(f"/api/v1/admin/users/{OTHER_USER_ID}/disable")
        assert resp.status_code == 409

        # Set agent to private
        other_client.patch(f"/api/v1/agents/{agent_id}", json={"visibility": "private"})

        # Second disable attempt succeeds
        resp2 = admin_client.patch(f"/api/v1/admin/users/{OTHER_USER_ID}/disable")
        assert resp2.status_code == 200

    def test_disable_succeeds_after_agent_transferred(self, admin_client, other_client):
        agent_resp = other_client.post(
            "/api/v1/agents",
            json={
                "name": "Transfer Me",
                "system_prompt": "You are helpful.",
                "visibility": "public",
            },
        )
        if agent_resp.status_code not in (200, 201):
            pytest.skip("Agent endpoint not yet implemented (Sprint 4)")

        agent_id = agent_resp.json()["id"]

        # Transfer agent to REGULAR_USER
        transfer_resp = admin_client.patch(
            f"/api/v1/admin/users/{OTHER_USER_ID}/transfer-agent",
            json={"agent_id": agent_id, "new_owner_id": REGULAR_USER_ID},
        )
        assert transfer_resp.status_code == 200

        # Now disable should succeed
        resp = admin_client.patch(f"/api/v1/admin/users/{OTHER_USER_ID}/disable")
        assert resp.status_code == 200

    def test_non_admin_cannot_disable(self, auth_client):
        resp = auth_client.patch(f"/api/v1/admin/users/{OTHER_USER_ID}/disable")
        assert resp.status_code == 403

    def test_disable_nonexistent_user_returns_404(self, admin_client):
        resp = admin_client.patch(
            "/api/v1/admin/users/00000000-0000-0000-0000-999999999999/disable"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/admin/users/{id}/enable
# ---------------------------------------------------------------------------

class TestEnableUser:
    def test_enable_disabled_user(self, admin_client):
        # Disable first
        admin_client.patch(f"/api/v1/admin/users/{OTHER_USER_ID}/disable")
        # Then enable
        resp = admin_client.patch(f"/api/v1/admin/users/{OTHER_USER_ID}/enable")
        assert resp.status_code == 200
        assert resp.json().get("disabled_at") is None

    def test_enable_already_active_user_is_idempotent(self, admin_client):
        # Enable a user that isn't disabled — should not error
        resp = admin_client.patch(f"/api/v1/admin/users/{OTHER_USER_ID}/enable")
        assert resp.status_code == 200

    def test_non_admin_cannot_enable(self, auth_client):
        resp = auth_client.patch(f"/api/v1/admin/users/{OTHER_USER_ID}/enable")
        assert resp.status_code == 403

    def test_enable_nonexistent_user_returns_404(self, admin_client):
        resp = admin_client.patch(
            "/api/v1/admin/users/00000000-0000-0000-0000-999999999999/enable"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/admin/users/{id}/transfer-agent
# ---------------------------------------------------------------------------

class TestTransferAgent:
    def test_transfer_agent_changes_ownership(self, admin_client, other_client):
        agent_resp = other_client.post(
            "/api/v1/agents",
            json={
                "name": "Transferable",
                "system_prompt": "You are helpful.",
                "visibility": "public",
            },
        )
        if agent_resp.status_code not in (200, 201):
            pytest.skip("Agent endpoint not yet implemented (Sprint 4)")

        agent_id = agent_resp.json()["id"]

        resp = admin_client.patch(
            f"/api/v1/admin/users/{OTHER_USER_ID}/transfer-agent",
            json={"agent_id": agent_id, "new_owner_id": REGULAR_USER_ID},
        )
        assert resp.status_code == 200

    def test_transfer_requires_agent_id_and_new_owner(self, admin_client):
        resp = admin_client.patch(
            f"/api/v1/admin/users/{OTHER_USER_ID}/transfer-agent",
            json={},
        )
        assert resp.status_code == 422

    def test_non_admin_cannot_transfer(self, auth_client):
        resp = auth_client.patch(
            f"/api/v1/admin/users/{OTHER_USER_ID}/transfer-agent",
            json={"agent_id": "some-id", "new_owner_id": REGULAR_USER_ID},
        )
        assert resp.status_code == 403
