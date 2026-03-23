"""
Route tests for AgentDefinition CRUD + AgentInstance lifecycle — KIN-293 (KIN-287, KIN-288).
"""
from __future__ import annotations

import pytest

from tests.conftest import TEST_AGENT_ID, TEST_USER_ID, ok, empty, seq


AGENT_ROW = {
    "id": TEST_AGENT_ID,
    "owner_id": TEST_USER_ID,
    "name": "My Coach",
    "instructions": "You are a Socratic coach.",
    "type": "custom",
    "visibility": "private",
    "mcp_enabled": False,
    "created_at": "2026-01-01T00:00:00Z",
}

INSTANCE_ROW = {
    "id": "inst-001",
    "agent_definition_id": TEST_AGENT_ID,
    "user_id": TEST_USER_ID,
    "framework_overrides": {"pinned": [], "excluded": []},
    "created_at": "2026-01-01T00:00:00Z",
}

OTHER_AGENT_ID = "00000000-0000-0000-0000-000000000041"
PUBLIC_AGENT_ID = "00000000-0000-0000-0000-000000000042"

OTHER_USER_PRIVATE_AGENT = {
    **AGENT_ROW,
    "id": OTHER_AGENT_ID,
    "owner_id": "00000000-0000-0000-0000-000000000099",
    "visibility": "private",
}

PUBLIC_AGENT = {
    **AGENT_ROW,
    "id": PUBLIC_AGENT_ID,
    "visibility": "public",
}


class TestListAgents:
    def test_returns_owned_and_public(self, client, sb):
        seq(sb, ok([AGENT_ROW]), ok([PUBLIC_AGENT]))
        r = client.get("/api/v1/agents")
        assert r.status_code == 200
        ids = [a["id"] for a in r.json()]
        assert TEST_AGENT_ID in ids
        assert PUBLIC_AGENT_ID in ids

    def test_deduplicates(self, client, sb):
        """Own public agent should not appear twice."""
        own_public = {**AGENT_ROW, "visibility": "public"}
        seq(sb, ok([own_public]), ok([]))  # public query excludes own
        r = client.get("/api/v1/agents")
        assert r.status_code == 200
        assert len(r.json()) == 1


class TestCreateAgent:
    def test_success(self, client, sb):
        seq(sb, empty(), ok([AGENT_ROW]), empty(), ok([INSTANCE_ROW]))
        r = client.post(
            "/api/v1/agents",
            json={"name": "My Coach", "instructions": "Be helpful."},
        )
        assert r.status_code == 201
        assert r.json()["name"] == "My Coach"

    def test_public_without_instructions_returns_422(self, client, sb):
        r = client.post(
            "/api/v1/agents",
            json={"name": "Public Agent", "visibility": "public", "instructions": ""},
        )
        assert r.status_code == 400

    def test_duplicate_name_returns_409(self, client, sb):
        seq(sb, ok({"id": "existing"}))  # name uniqueness check
        r = client.post(
            "/api/v1/agents",
            json={"name": "My Coach"},
        )
        assert r.status_code == 409

    def test_invalid_type_returns_422(self, client, sb):
        r = client.post(
            "/api/v1/agents",
            json={"name": "Bad", "type": "autonomous"},
        )
        assert r.status_code == 422


class TestGetAgent:
    def test_owner_can_get(self, client, sb):
        sb.execute.return_value = ok(AGENT_ROW)
        r = client.get(f"/api/v1/agents/{TEST_AGENT_ID}")
        assert r.status_code == 200
        assert r.json()["id"] == TEST_AGENT_ID

    def test_other_user_private_returns_403(self, client, sb):
        sb.execute.return_value = ok(OTHER_USER_PRIVATE_AGENT)
        r = client.get(f"/api/v1/agents/{OTHER_AGENT_ID}")
        assert r.status_code == 403

    def test_public_agent_accessible_by_non_owner(self, client, sb):
        sb.execute.return_value = ok(PUBLIC_AGENT)
        r = client.get(f"/api/v1/agents/{PUBLIC_AGENT_ID}")
        assert r.status_code == 200

    def test_not_found_returns_404(self, client, sb):
        sb.execute.return_value = empty()
        r = client.get(f"/api/v1/agents/{TEST_AGENT_ID}")
        assert r.status_code == 404


class TestUpdateAgent:
    def test_owner_can_update(self, client, sb):
        updated = {**AGENT_ROW, "name": "Renamed"}
        seq(sb, ok(AGENT_ROW), ok([updated]))
        r = client.patch(f"/api/v1/agents/{TEST_AGENT_ID}", json={"name": "Renamed"})
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"

    def test_non_owner_returns_403(self, client, sb):
        sb.execute.return_value = empty()  # _require_owner fails
        r = client.patch(f"/api/v1/agents/{TEST_AGENT_ID}", json={"name": "X"})
        assert r.status_code == 403


class TestDeleteAgent:
    def test_private_agent_deleted(self, client, sb):
        seq(sb, ok(AGENT_ROW), ok([]))
        r = client.delete(f"/api/v1/agents/{TEST_AGENT_ID}")
        assert r.status_code == 204

    def test_public_with_other_invokers_blocked(self, client, sb):
        seq(
            sb,
            ok(PUBLIC_AGENT),               # _require_owner
            ok([{"id": "inst-other"}]),     # external instances exist
        )
        r = client.delete(f"/api/v1/agents/{PUBLIC_AGENT_ID}")
        assert r.status_code == 409

    def test_public_no_external_invokers_succeeds(self, client, sb):
        seq(
            sb,
            ok(PUBLIC_AGENT),   # _require_owner
            ok([]),             # no external instances
            ok([]),             # delete
        )
        r = client.delete(f"/api/v1/agents/{PUBLIC_AGENT_ID}")
        assert r.status_code == 204

    def test_not_owner_returns_403(self, client, sb):
        sb.execute.return_value = empty()
        r = client.delete(f"/api/v1/agents/{TEST_AGENT_ID}")
        assert r.status_code == 403


class TestAgentInstance:
    def test_get_instance_creates_on_first_call(self, client, sb):
        seq(
            sb,
            ok(AGENT_ROW),      # _get_agent visibility check
            empty(),            # instance not found → create
            ok([INSTANCE_ROW]), # insert instance
        )
        r = client.get(f"/api/v1/agents/{TEST_AGENT_ID}/instance")
        assert r.status_code == 200
        assert r.json()["agent_definition_id"] == TEST_AGENT_ID

    def test_get_instance_returns_existing(self, client, sb):
        seq(
            sb,
            ok(AGENT_ROW),    # _get_agent
            ok(INSTANCE_ROW), # instance already exists
        )
        r = client.get(f"/api/v1/agents/{TEST_AGENT_ID}/instance")
        assert r.status_code == 200
        assert r.json()["id"] == "inst-001"

    def test_update_framework_overrides(self, client, sb):
        overrides = {"pinned": ["fw-1"], "excluded": []}
        updated_instance = {**INSTANCE_ROW, "framework_overrides": overrides}
        seq(
            sb,
            ok(AGENT_ROW),           # _get_agent
            ok(INSTANCE_ROW),        # _get_or_create_instance
            ok([updated_instance]),  # update
        )
        r = client.patch(
            f"/api/v1/agents/{TEST_AGENT_ID}/instance",
            json={"framework_overrides": overrides},
        )
        assert r.status_code == 200
        assert r.json()["framework_overrides"]["pinned"] == ["fw-1"]

    def test_inaccessible_agent_returns_404_or_403(self, client, sb):
        sb.execute.return_value = empty()
        r = client.get(f"/api/v1/agents/{TEST_AGENT_ID}/instance")
        assert r.status_code in (403, 404)
