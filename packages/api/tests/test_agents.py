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

from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID

TEST_AGENT_ID = str(uuid4())
TEST_INSTANCE_ID = str(uuid4())
OTHER_USER_ID = str(uuid4())

PATCH_TARGET = "app.api.routes.agents.get_supabase_client"
PATCH_DISPATCHER = "app.api.routes.agents.get_task_dispatcher"
PATCH_UNIQUE_SLUG = "app.api.routes.agents._ensure_unique_slug"


def _agent_row(
    agent_id: str = TEST_AGENT_ID,
    owner_id: str = TEST_USER_ID,
    visibility: str = "private",
    instructions: str = "Do the thing",
    name: str = "Test Agent",
    slug: str = "test-agent",
    agent_type: str = "custom",
) -> dict:
    return {
        "id": agent_id,
        "owner_id": owner_id,
        "name": name,
        "slug": slug,
        "instructions": instructions,
        "type": agent_type,
        "visibility": visibility,
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
# Slug generation (unit tests for _agent_slug)
# ---------------------------------------------------------------------------


class TestAgentSlug:
    def test_basic_slug(self):
        from app.api.routes.agents import _agent_slug
        assert _agent_slug("My Cool Agent") == "my-cool-agent"

    def test_special_chars(self):
        from app.api.routes.agents import _agent_slug
        assert _agent_slug("Nate B. Jones (v2)") == "nate-b-jones-v2"

    def test_leading_trailing_hyphens(self):
        from app.api.routes.agents import _agent_slug
        assert _agent_slug("---hello---") == "hello"

    def test_empty_name(self):
        from app.api.routes.agents import _agent_slug
        assert _agent_slug("!!!") == "agent"

    def test_truncation_at_60(self):
        from app.api.routes.agents import _agent_slug
        long_name = "a" * 80
        slug = _agent_slug(long_name)
        assert len(slug) <= 60

    def test_truncation_strips_trailing_hyphen(self):
        from app.api.routes.agents import _agent_slug
        # Name that produces a slug ending in hyphen at position 60
        name = "a" * 59 + " b" * 20
        slug = _agent_slug(name)
        assert len(slug) <= 60
        assert not slug.endswith("-")


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
        with patch(PATCH_TARGET, return_value=mock_db), \
             patch(PATCH_UNIQUE_SLUG, new_callable=AsyncMock, return_value="test-agent"):
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
        assert data["slug"] == "test-agent"

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

    def test_create_allows_empty_instructions_for_private(self, client):
        """KIN-365: instructions defaults to "" — private agents can be created without instructions."""
        row = _agent_row(instructions="", name="Draft Agent", slug="draft-agent")
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[row]
        )
        with patch(PATCH_TARGET, return_value=mock_db), \
             patch(PATCH_UNIQUE_SLUG, new_callable=AsyncMock, return_value="draft-agent"):
            response = client.post(
                "/api/v1/agents",
                json={
                    "name": "Draft Agent",
                    "type": "custom",
                    # instructions omitted — should use default ""
                },
            )
        assert response.status_code == 200
        assert response.json()["name"] == "Draft Agent"

    def test_create_allows_empty_instructions_explicitly(self, client):
        """KIN-365: explicit empty string instructions also allowed for private agents."""
        row = _agent_row(instructions="")
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[row]
        )
        with patch(PATCH_TARGET, return_value=mock_db), \
             patch(PATCH_UNIQUE_SLUG, new_callable=AsyncMock, return_value="test-agent"):
            response = client.post(
                "/api/v1/agents",
                json={
                    "name": "Empty Instructions Agent",
                    "instructions": "",
                    "type": "custom",
                    "visibility": "private",
                },
            )
        assert response.status_code == 200


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
        updated = {**original, "name": "Renamed Agent", "slug": "renamed-agent"}
        mock_db = MagicMock()
        # Fetch for ownership check
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=original)
        )
        # Update
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[updated])
        )
        with patch(PATCH_TARGET, return_value=mock_db), \
             patch(PATCH_UNIQUE_SLUG, new_callable=AsyncMock, return_value="renamed-agent"):
            response = client.patch(
                f"/api/v1/agents/{TEST_AGENT_ID}", json={"name": "Renamed Agent"}
            )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed Agent"
        assert response.json()["slug"] == "renamed-agent"

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


# ---------------------------------------------------------------------------
# Framework mutation endpoints (create + patch)
# ---------------------------------------------------------------------------


class TestFrameworkMutations:
    def test_create_framework_200(self, client):
        """Owner posts valid body — 200, returned row has correct name."""
        agent = _agent_row()
        fw_row = _framework_row(agent_id=TEST_AGENT_ID)
        fw_row = {**fw_row, "name": "My New Framework"}
        mock_db = MagicMock()

        # Agent fetch (uses .single())
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        # Insert
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[fw_row]
        )

        with patch(PATCH_TARGET, return_value=mock_db), patch(PATCH_DISPATCHER):
            response = client.post(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks",
                json={
                    "name": "My New Framework",
                    "when_to_apply": ["when facing ambiguity"],
                    "principles": ["Be clear"],
                    "confidence": "high",
                },
            )
        assert response.status_code == 200
        assert response.json()["name"] == "My New Framework"

    def test_create_framework_403_non_owner(self, client):
        """Non-owner posting to another user's agent — 403."""
        agent = _agent_row(owner_id=OTHER_USER_ID, visibility="public")
        mock_db = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks",
                json={
                    "name": "Hijack Framework",
                    "when_to_apply": ["always"],
                    "principles": ["own it"],
                    "confidence": "high",
                },
            )
        assert response.status_code == 403

    def test_create_framework_400_empty_when_to_apply(self, client):
        """when_to_apply: [] — 400 validation error."""
        agent = _agent_row()
        mock_db = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks",
                json={
                    "name": "Bad Framework",
                    "when_to_apply": [],
                    "principles": ["Be clear"],
                    "confidence": "high",
                },
            )
        assert response.status_code == 400

    def test_patch_framework_200(self, client):
        """Owner patches name — 200, returned name is updated."""
        agent = _agent_row()
        fw_id = str(uuid4())
        fw = _framework_row(fw_id=fw_id, agent_id=TEST_AGENT_ID)
        updated_fw = {**fw, "name": "Renamed Framework"}
        mock_db = MagicMock()

        # Agent fetch and framework fetch both use .single(); use side_effect to differentiate
        single_results = [MagicMock(data=agent), MagicMock(data=fw)]
        call_count = {"n": 0}

        def _single_execute():
            idx = call_count["n"]
            call_count["n"] += 1
            return single_results[idx] if idx < len(single_results) else MagicMock(data=None)

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = (
            _single_execute
        )
        # The framework fetch uses .eq().eq().single() — same chain resolves to same mock
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.side_effect = (
            _single_execute
        )
        # Update
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[updated_fw])
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/{fw_id}",
                json={"name": "Renamed Framework"},
            )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed Framework"

    def test_patch_framework_403_non_owner(self, client):
        """Non-owner cannot patch a framework — 403."""
        agent = _agent_row(owner_id=OTHER_USER_ID, visibility="public")
        fw_id = str(uuid4())
        mock_db = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/{fw_id}",
                json={"name": "Hijack"},
            )
        assert response.status_code == 403

    def test_patch_framework_404_not_found(self, client):
        """Framework not found under this agent — 404."""
        agent = _agent_row()
        fw_id = str(uuid4())
        mock_db = MagicMock()

        # Agent fetch succeeds, framework fetch returns None
        single_results = [MagicMock(data=agent), MagicMock(data=None)]
        call_count = {"n": 0}

        def _single_execute():
            idx = call_count["n"]
            call_count["n"] += 1
            return single_results[idx] if idx < len(single_results) else MagicMock(data=None)

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = (
            _single_execute
        )
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.side_effect = (
            _single_execute
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/{fw_id}",
                json={"name": "Ghost"},
            )
        assert response.status_code == 404

    def test_upload_adds_new_and_updates_existing(self, client):
        """1 new framework + 1 existing → added:1, updated:1, retained:0, failed:[]"""
        agent = _agent_row()
        existing_fw_uuid = str(uuid4())
        mock_db = MagicMock()

        # Agent fetch (uses .select().eq().single().execute())
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )

        # Fetch existing frameworks (uses .select().eq().execute() — single .eq(), no .single())
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"id": existing_fw_uuid, "framework_id": "existing-fw"}])
        )

        # Update existing framework (uses .update().eq().execute())
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"id": existing_fw_uuid, "framework_id": "existing-fw"}])
        )

        # Insert new framework (uses .insert().execute())
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": str(uuid4()), "framework_id": "new-fw"}]
        )

        with patch(PATCH_TARGET, return_value=mock_db), patch(PATCH_DISPATCHER):
            response = client.post(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/upload",
                json={
                    "frameworks": [
                        {
                            "name": "Existing",
                            "framework_id": "existing-fw",
                            "when_to_apply": ["trigger"],
                            "confidence": "high",
                            "principles": ["p1"],
                        },
                        {
                            "name": "New One",
                            "framework_id": "new-fw",
                            "when_to_apply": ["trigger2"],
                            "confidence": "medium",
                            "principles": ["p2"],
                        },
                    ]
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["added"] == 1
        assert data["updated"] == 1
        assert data["retained"] == 0
        assert data["failed"] == []

    def test_upload_skips_invalid_items(self, client):
        """Item missing when_to_apply → appears in failed list, valid item processed."""
        agent = _agent_row()
        mock_db = MagicMock()

        # Agent fetch (uses .single())
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )

        # Fetch existing frameworks — empty (uses .select().eq().execute(), no .single())
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        # Insert new valid framework
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": str(uuid4()), "framework_id": "valid-fw"}]
        )

        with patch(PATCH_TARGET, return_value=mock_db), patch(PATCH_DISPATCHER):
            response = client.post(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/upload",
                json={
                    "frameworks": [
                        {
                            # Missing when_to_apply
                            "name": "Bad Item",
                            "framework_id": "bad-fw",
                            "confidence": "high",
                            "principles": ["p1"],
                        },
                        {
                            "name": "Valid Item",
                            "framework_id": "valid-fw",
                            "when_to_apply": ["trigger"],
                            "confidence": "medium",
                            "principles": ["p2"],
                        },
                    ]
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["added"] == 1
        assert len(data["failed"]) == 1

    def test_upload_403_non_owner(self, client):
        """Non-owner gets 403."""
        agent = _agent_row(owner_id=OTHER_USER_ID, visibility="public")
        mock_db = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/upload",
                json={
                    "frameworks": [
                        {
                            "name": "Framework",
                            "framework_id": "fw-1",
                            "when_to_apply": ["trigger"],
                            "confidence": "high",
                            "principles": ["p1"],
                        }
                    ]
                },
            )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Delete-all frameworks — KIN-415
# ---------------------------------------------------------------------------


class TestDeleteAllFrameworks:
    def test_delete_all_returns_count(self, client):
        """Owner deletes all frameworks — returns deleted_count."""
        agent = _agent_row()
        fw1 = _framework_row(fw_id=str(uuid4()), agent_id=TEST_AGENT_ID)
        fw2 = _framework_row(fw_id=str(uuid4()), agent_id=TEST_AGENT_ID)
        mock_db = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[fw1, fw2])
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/agents/{TEST_AGENT_ID}/frameworks")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 2
        assert data["agent_id"] == TEST_AGENT_ID

    def test_delete_all_empty_returns_zero(self, client):
        """No frameworks to delete — returns deleted_count: 0."""
        agent = _agent_row()
        mock_db = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )

        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/agents/{TEST_AGENT_ID}/frameworks")
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 0

    def test_delete_all_403_non_owner(self, client):
        """Non-owner cannot delete all frameworks — returns 403."""
        agent = _agent_row(owner_id=OTHER_USER_ID, visibility="public")
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/agents/{TEST_AGENT_ID}/frameworks")
        assert response.status_code == 403

    def test_delete_all_404_agent_not_found(self, client):
        """Nonexistent agent returns 404."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=None)
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/agents/{str(uuid4())}/frameworks")
        assert response.status_code == 404
