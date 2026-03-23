"""
Tests for KIN-319: AgentDefinition CRUD + AgentInstance endpoints.

Covers:
  - List agents (TestListAgents)
  - Create agent (TestCreateAgent)
  - Get single agent (TestGetAgent)
  - Update agent (TestUpdateAgent)
  - Delete agent (TestDeleteAgent)
  - Agent instance get-or-create + update (TestAgentInstance)

All Supabase calls are mocked. Uses client fixture from conftest.py.
Schema ref: docs/db-schema-spec.md (agent_definitions, agent_instances)
"""

from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID

TEST_AGENT_ID = str(uuid4())
TEST_INSTANCE_ID = str(uuid4())
OTHER_USER_ID = str(uuid4())

PATCH_TARGET = "app.api.routes.agents.get_supabase_client"


def _agent_row(
    agent_id: str = TEST_AGENT_ID,
    owner_id: str = TEST_USER_ID,
    visibility: str = "private",
    instructions: str = "Do the thing",
    name: str = "Test Agent",
    agent_type: str = "custom",
) -> dict:
    return {
        "id": agent_id,
        "owner_id": owner_id,
        "name": name,
        "instructions": instructions,
        "type": agent_type,
        "visibility": visibility,
        "knowledge_base_id": None,
        "mcp_enabled": False,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _instance_row(
    instance_id: str = TEST_INSTANCE_ID,
    agent_id: str = TEST_AGENT_ID,
    user_id: str = TEST_USER_ID,
) -> dict:
    return {
        "id": instance_id,
        "agent_definition_id": agent_id,
        "user_id": user_id,
        "framework_overrides": {"pinned": [], "excluded": []},
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# List agents
# ---------------------------------------------------------------------------


class TestListAgents:
    def test_list_returns_agents(self, client):
        owned = _agent_row()
        public = _agent_row(agent_id=str(uuid4()), owner_id=OTHER_USER_ID, visibility="public")
        mock_db = MagicMock()
        # First call: owned agents; second call: public agents
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[owned])
        )
        mock_db.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value = (
            MagicMock(data=[public])
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get("/api/v1/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_empty(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        mock_db.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get("/api/v1/agents")
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Create agent
# ---------------------------------------------------------------------------


class TestCreateAgent:
    def test_create_returns_agent(self, client):
        row = _agent_row()
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[row]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/agents",
                json={
                    "name": "Test Agent",
                    "instructions": "Do the thing",
                    "type": "custom",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Agent"
        assert data["type"] == "custom"

    def test_create_rejects_public_without_instructions(self, client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            response = client.post(
                "/api/v1/agents",
                json={
                    "name": "Public Agent",
                    "instructions": "",
                    "type": "custom",
                    "visibility": "public",
                },
            )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Get single agent
# ---------------------------------------------------------------------------


class TestGetAgent:
    def test_get_owned_agent(self, client):
        row = _agent_row()
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=row)
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/agents/{TEST_AGENT_ID}")
        assert response.status_code == 200
        assert response.json()["id"] == TEST_AGENT_ID

    def test_get_public_agent_non_owner(self, client):
        row = _agent_row(owner_id=OTHER_USER_ID, visibility="public")
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=row)
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/agents/{TEST_AGENT_ID}")
        assert response.status_code == 200

    def test_get_private_agent_non_owner_returns_404(self, client):
        row = _agent_row(owner_id=OTHER_USER_ID, visibility="private")
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=row)
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/agents/{TEST_AGENT_ID}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update agent
# ---------------------------------------------------------------------------


class TestUpdateAgent:
    def test_patch_name(self, client):
        original = _agent_row()
        updated = {**original, "name": "Renamed Agent"}
        mock_db = MagicMock()
        # Fetch for ownership check
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=original)
        )
        # Update
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[updated])
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/agents/{TEST_AGENT_ID}", json={"name": "Renamed Agent"}
            )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed Agent"

    def test_patch_403_non_owner(self, client):
        row = _agent_row(owner_id=OTHER_USER_ID, visibility="public")
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=row)
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/agents/{TEST_AGENT_ID}", json={"name": "Hijack"}
            )
        assert response.status_code == 403

    def test_patch_public_blocked_without_instructions(self, client):
        row = _agent_row(instructions="Some instructions")
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=row)
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/agents/{TEST_AGENT_ID}",
                json={"visibility": "public", "instructions": ""},
            )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Delete agent
# ---------------------------------------------------------------------------


class TestDeleteAgent:
    def test_delete_204(self, client):
        row = _agent_row()
        mock_db = MagicMock()
        # Ownership check
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=row)
        )
        # Check instances (no non-owner instances)
        mock_db.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        # Delete
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[row])
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/agents/{TEST_AGENT_ID}")
        assert response.status_code == 204

    def test_delete_403_non_owner(self, client):
        row = _agent_row(owner_id=OTHER_USER_ID, visibility="public")
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=row)
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/agents/{TEST_AGENT_ID}")
        assert response.status_code == 403

    def test_delete_blocked_if_public_with_invokers(self, client):
        row = _agent_row(visibility="public")
        instance = _instance_row(user_id=OTHER_USER_ID)
        mock_db = MagicMock()
        # Ownership check
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=row)
        )
        # Non-owner instances exist
        mock_db.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value = (
            MagicMock(data=[instance])
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/agents/{TEST_AGENT_ID}")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Agent instance (get-or-create + patch overrides)
# ---------------------------------------------------------------------------


class TestAgentInstance:
    def test_get_or_create_existing(self, client):
        """SELECT finds existing instance — no insert needed."""
        agent = _agent_row()
        instance = _instance_row()
        mock_db = MagicMock()
        # Step 0: agent access check (uses .single())
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        # Step 1: instance SELECT (no .single())
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[instance])
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/agents/{TEST_AGENT_ID}/instance")
        assert response.status_code == 200
        assert response.json()["id"] == TEST_INSTANCE_ID

    def test_get_or_create_creates_new(self, client):
        """SELECT finds nothing → INSERT ON CONFLICT DO NOTHING → re-SELECT returns new row."""
        agent = _agent_row()
        instance = _instance_row()
        mock_db = MagicMock()
        # Step 0: agent access check (uses .single())
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        # Step 1 + re-SELECT: first call empty, second call returns row
        select_results = [MagicMock(data=[]), MagicMock(data=[instance])]
        call_count = {"n": 0}

        def _select_side_effect():
            idx = call_count["n"]
            call_count["n"] += 1
            return select_results[idx] if idx < len(select_results) else MagicMock(data=[instance])

        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.side_effect = (
            _select_side_effect
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/agents/{TEST_AGENT_ID}/instance")
        assert response.status_code == 200
        assert response.json()["id"] == TEST_INSTANCE_ID

    def test_patch_instance_overrides(self, client):
        instance = _instance_row()
        updated = {**instance, "framework_overrides": {"pinned": ["fw-1"], "excluded": []}}
        mock_db = MagicMock()
        # Fetch instance by agent_definition_id + user_id (uses .single())
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=instance)
        )
        # Update
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[updated])
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/agents/{TEST_AGENT_ID}/instance",
                json={"framework_overrides": {"pinned": ["fw-1"], "excluded": []}},
            )
        assert response.status_code == 200
        assert response.json()["framework_overrides"]["pinned"] == ["fw-1"]

    def test_patch_instance_404_not_found(self, client):
        """404 when no instance exists for this agent + user."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=None)
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/agents/{TEST_AGENT_ID}/instance",
                json={"framework_overrides": {"pinned": [], "excluded": []}},
            )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Framework endpoints (list + delete)
# ---------------------------------------------------------------------------


def _framework_row(fw_id=None, agent_id=None):
    return {
        "id": fw_id or str(uuid4()),
        "agent_definition_id": agent_id or TEST_AGENT_ID,
        "framework_id": "test-framework",
        "name": "Test Framework",
        "description": "A test framework",
        "category": "strategy",
        "when_to_apply": ["when facing a complex problem"],
        "confidence": "high",
        "origin": "manual",
        "principles": ["Think first"],
        "steps": [],
        "example_application": None,
        "related_frameworks": [],
        "source_posts": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


class TestFrameworkEndpoints:
    def test_list_frameworks_returns_list(self, client):
        """Owner can list frameworks for their agent."""
        agent = _agent_row()
        fw = _framework_row(agent_id=TEST_AGENT_ID)
        mock_db = MagicMock()

        responses = [MagicMock(data=agent), MagicMock(data=[fw])]
        call_count = {"n": 0}

        def _execute_side_effect():
            idx = call_count["n"]
            call_count["n"] += 1
            return responses[idx]

        # First call: fetch agent (uses .single())
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = (
            _execute_side_effect
        )
        # Second call: list frameworks (no .single())
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
            MagicMock(data=[fw])
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/agents/{TEST_AGENT_ID}/frameworks")
        assert response.status_code == 200
        data = response.json()
        assert "frameworks" in data
        assert len(data["frameworks"]) == 1
        assert data["frameworks"][0]["framework_id"] == "test-framework"

    def test_list_frameworks_empty(self, client):
        """Owner agent with no frameworks returns empty list."""
        agent = _agent_row()
        mock_db = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
            MagicMock(data=[])
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/agents/{TEST_AGENT_ID}/frameworks")
        assert response.status_code == 200
        assert response.json() == {"frameworks": []}

    def test_list_frameworks_404_private_non_owner(self, client):
        """Private agent owned by someone else returns 404 (no existence leak)."""
        agent = _agent_row(owner_id=OTHER_USER_ID, visibility="private")
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/agents/{TEST_AGENT_ID}/frameworks")
        assert response.status_code == 404

    def test_delete_framework_204(self, client):
        """Owner can delete a framework — returns 204."""
        agent = _agent_row()
        fw_id = str(uuid4())
        fw = _framework_row(fw_id=fw_id, agent_id=TEST_AGENT_ID)
        mock_db = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[fw])
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/{fw_id}")
        assert response.status_code == 204

    def test_delete_framework_403_non_owner(self, client):
        """Non-owner cannot delete a framework — returns 403."""
        agent = _agent_row(owner_id=OTHER_USER_ID, visibility="public")
        fw_id = str(uuid4())
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/{fw_id}")
        assert response.status_code == 403

    def test_delete_framework_404_not_found(self, client):
        """Delete a framework_id that doesn't exist under this agent — returns 404."""
        agent = _agent_row()
        fw_id = str(uuid4())
        mock_db = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/{fw_id}")
        assert response.status_code == 404
