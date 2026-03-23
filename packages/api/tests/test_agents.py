"""
Tests for AgentDefinition CRUD + AgentInstance endpoints — KIN-293.

Tests cover:
  AgentDefinition:
  - GET  /api/v1/agents        — list owned + public agents
  - POST /api/v1/agents        — create agent
  - GET  /api/v1/agents/:id    — get single agent (owned/public)
  - PATCH /api/v1/agents/:id   — update (owner only)
  - DELETE /api/v1/agents/:id  — delete (owner only, blocked if public + invokers)

  AgentInstance:
  - GET  /api/v1/agents/:id/instance — get-or-create
  - PATCH /api/v1/agents/:id/instance — update framework_overrides

Spec ref: docs/specs/agents.md
KIN-287: AgentDefinition CRUD
KIN-288: AgentInstance auto-create
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

PATCH_DB = "app.api.routes.agents.get_supabase_client"

USER_ID = "00000000-0000-0000-0000-000000000001"  # matches conftest TEST_USER_ID
OTHER_USER_ID = "00000000-0000-0000-0000-000000000002"
AGENT_ID = str(uuid4())
INSTANCE_ID = str(uuid4())

_OWNED_AGENT = {
    "id": AGENT_ID,
    "owner_id": USER_ID,
    "name": "My Agent",
    "instructions": "You are a strategist.",
    "type": "custom",
    "visibility": "private",
    "mcp_enabled": False,
    "knowledge_base_id": None,
    "created_at": "2026-03-23T00:00:00",
    "updated_at": "2026-03-23T00:00:00",
}

_PUBLIC_AGENT = {
    "id": str(uuid4()),
    "owner_id": OTHER_USER_ID,
    "name": "Public Agent",
    "instructions": "You are public.",
    "type": "custom",
    "visibility": "public",
    "mcp_enabled": False,
    "knowledge_base_id": None,
    "created_at": "2026-03-23T00:00:00",
    "updated_at": "2026-03-23T00:00:00",
}

_INSTANCE = {
    "id": INSTANCE_ID,
    "agent_definition_id": AGENT_ID,
    "user_id": USER_ID,
    "framework_overrides": {"pinned": [], "excluded": []},
    "created_at": "2026-03-23T00:00:00",
    "updated_at": "2026-03-23T00:00:00",
}


def _mock_chain(return_data, *, count: int = 0):
    result = MagicMock()
    result.data = return_data
    result.count = count
    chain = MagicMock()
    for method in (
        "select", "eq", "neq", "is_", "order", "limit",
        "maybe_single", "insert", "update", "delete", "in_",
    ):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = result
    return chain, result


def _make_supabase(
    all_agents=None,
    single_agent=None,
    instance=None,
    instance_count=0,
):
    """Flexible supabase mock for agent tests."""
    sb = MagicMock()

    def _table(name):
        if name == "agent_definitions":
            chain, _ = _mock_chain(
                all_agents if all_agents is not None else [],
            )
            if single_agent is not None:
                chain.maybe_single.return_value = chain
                chain.execute.return_value = MagicMock(data=single_agent)
            return chain
        elif name == "agent_instances":
            chain, r = _mock_chain(
                instance,
                count=instance_count,
            )
            if instance:
                insert_chain, _ = _mock_chain([instance])
                chain.insert.return_value = insert_chain
            return chain
        else:
            chain, _ = _mock_chain(None)
            return chain

    sb.table.side_effect = _table
    return sb


# ---------------------------------------------------------------------------
# GET /api/v1/agents
# ---------------------------------------------------------------------------


class TestListAgents:
    def test_returns_owned_and_public_agents(self, client):
        sb = _make_supabase(all_agents=[_OWNED_AGENT, _PUBLIC_AGENT])
        with patch(PATCH_DB, return_value=sb):
            res = client.get("/api/v1/agents")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2

    def test_excludes_private_agents_from_other_users(self, client):
        other_private = {**_PUBLIC_AGENT, "visibility": "private", "owner_id": OTHER_USER_ID}
        sb = _make_supabase(all_agents=[_OWNED_AGENT, other_private])
        with patch(PATCH_DB, return_value=sb):
            res = client.get("/api/v1/agents")
        assert res.status_code == 200
        data = res.json()
        # Only owned agent returned; other user's private agent filtered out
        assert len(data) == 1
        assert data[0]["id"] == AGENT_ID

    def test_empty_list(self, client):
        sb = _make_supabase(all_agents=[])
        with patch(PATCH_DB, return_value=sb):
            res = client.get("/api/v1/agents")
        assert res.status_code == 200
        assert res.json() == []


# ---------------------------------------------------------------------------
# POST /api/v1/agents
# ---------------------------------------------------------------------------


class TestCreateAgent:
    def test_creates_agent(self, client):
        sb = MagicMock()
        chain, _ = _mock_chain([_OWNED_AGENT])
        sb.table.return_value = chain

        with patch(PATCH_DB, return_value=sb):
            res = client.post(
                "/api/v1/agents",
                json={"name": "My Agent", "instructions": "You are a strategist."},
            )
        assert res.status_code == 201
        assert res.json()["name"] == "My Agent"

    def test_422_for_empty_name(self, client):
        with patch(PATCH_DB, return_value=MagicMock()):
            res = client.post("/api/v1/agents", json={"name": "  "})
        assert res.status_code == 422

    def test_422_for_missing_name(self, client):
        with patch(PATCH_DB, return_value=MagicMock()):
            res = client.post("/api/v1/agents", json={})
        assert res.status_code == 422

    def test_422_public_without_instructions(self, client):
        with patch(PATCH_DB, return_value=MagicMock()):
            res = client.post(
                "/api/v1/agents",
                json={"name": "My Agent", "visibility": "public"},
            )
        assert res.status_code == 422

    def test_422_invalid_type(self, client):
        with patch(PATCH_DB, return_value=MagicMock()):
            res = client.post(
                "/api/v1/agents",
                json={"name": "My Agent", "type": "invalid_type"},
            )
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/agents/:id
# ---------------------------------------------------------------------------


class TestGetAgent:
    def test_returns_owned_agent(self, client):
        sb = _make_supabase(all_agents=[_OWNED_AGENT])
        with patch(PATCH_DB, return_value=sb):
            res = client.get(f"/api/v1/agents/{AGENT_ID}")
        assert res.status_code == 200
        assert res.json()["id"] == AGENT_ID

    def test_returns_public_agent_for_non_owner(self, client):
        sb = _make_supabase(all_agents=[_PUBLIC_AGENT])
        with patch(PATCH_DB, return_value=sb):
            res = client.get(f"/api/v1/agents/{_PUBLIC_AGENT['id']}")
        assert res.status_code == 200

    def test_404_for_private_agent_non_owner(self, client):
        private_other = {**_PUBLIC_AGENT, "visibility": "private", "owner_id": OTHER_USER_ID}
        sb = _make_supabase(all_agents=[private_other])
        with patch(PATCH_DB, return_value=sb):
            res = client.get(f"/api/v1/agents/{private_other['id']}")
        assert res.status_code == 404

    def test_404_when_not_found(self, client):
        sb = _make_supabase(all_agents=[])
        with patch(PATCH_DB, return_value=sb):
            res = client.get(f"/api/v1/agents/{uuid4()}")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/agents/:id
# ---------------------------------------------------------------------------


class TestUpdateAgent:
    def test_owner_can_update(self, client):
        sb = MagicMock()
        updated = {**_OWNED_AGENT, "name": "Updated Name"}

        def _table(name):
            if name == "agent_definitions":
                chain, _ = _mock_chain(updated)
                chain.maybe_single.return_value = chain
                chain.execute.return_value = MagicMock(data=_OWNED_AGENT)
                update_chain, _ = _mock_chain([updated])
                chain.update.return_value = update_chain
                return chain
            return _mock_chain(None)[0]

        sb.table.side_effect = _table

        with patch(PATCH_DB, return_value=sb):
            res = client.patch(
                f"/api/v1/agents/{AGENT_ID}",
                json={"name": "Updated Name"},
            )
        assert res.status_code == 200

    def test_403_for_non_owner(self, client):
        other_owned = {**_OWNED_AGENT, "owner_id": OTHER_USER_ID}
        sb = MagicMock()

        def _table(name):
            if name == "agent_definitions":
                chain, _ = _mock_chain(other_owned)
                chain.maybe_single.return_value = chain
                return chain
            return _mock_chain(None)[0]

        sb.table.side_effect = _table

        with patch(PATCH_DB, return_value=sb):
            res = client.patch(
                f"/api/v1/agents/{AGENT_ID}",
                json={"name": "Hack"},
            )
        assert res.status_code == 403

    def test_404_when_not_found(self, client):
        sb = MagicMock()

        def _table(name):
            if name == "agent_definitions":
                chain, _ = _mock_chain(None)
                chain.maybe_single.return_value = chain
                return chain
            return _mock_chain(None)[0]

        sb.table.side_effect = _table

        with patch(PATCH_DB, return_value=sb):
            res = client.patch(
                f"/api/v1/agents/{uuid4()}",
                json={"name": "Ghost"},
            )
        assert res.status_code == 404

    def test_422_set_public_without_instructions(self, client):
        agent_no_instructions = {**_OWNED_AGENT, "instructions": None}
        sb = MagicMock()

        def _table(name):
            if name == "agent_definitions":
                chain, _ = _mock_chain(agent_no_instructions)
                chain.maybe_single.return_value = chain
                chain.execute.return_value = MagicMock(data=agent_no_instructions)
                return chain
            return _mock_chain(None)[0]

        sb.table.side_effect = _table

        with patch(PATCH_DB, return_value=sb):
            res = client.patch(
                f"/api/v1/agents/{AGENT_ID}",
                json={"visibility": "public"},
            )
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/v1/agents/:id
# ---------------------------------------------------------------------------


class TestDeleteAgent:
    def test_owner_can_delete_private_agent(self, client):
        sb = MagicMock()

        def _table(name):
            if name == "agent_definitions":
                chain, _ = _mock_chain(_OWNED_AGENT)
                chain.maybe_single.return_value = chain
                chain.execute.return_value = MagicMock(data=_OWNED_AGENT)
                delete_chain, _ = _mock_chain([])
                chain.delete.return_value = delete_chain
                return chain
            elif name == "agent_instances":
                chain, _ = _mock_chain([], count=0)
                return chain
            return _mock_chain(None)[0]

        sb.table.side_effect = _table

        with patch(PATCH_DB, return_value=sb):
            res = client.delete(f"/api/v1/agents/{AGENT_ID}")
        assert res.status_code == 204

    def test_422_delete_public_with_invokers(self, client):
        public_owned = {**_OWNED_AGENT, "visibility": "public"}
        sb = MagicMock()

        def _table(name):
            if name == "agent_definitions":
                chain, _ = _mock_chain(public_owned)
                chain.maybe_single.return_value = chain
                chain.execute.return_value = MagicMock(data=public_owned)
                return chain
            elif name == "agent_instances":
                # 3 invokers from other users
                chain, _ = _mock_chain([], count=3)
                return chain
            return _mock_chain(None)[0]

        sb.table.side_effect = _table

        with patch(PATCH_DB, return_value=sb):
            res = client.delete(f"/api/v1/agents/{AGENT_ID}")
        assert res.status_code == 422

    def test_403_non_owner_cannot_delete(self, client):
        other_owned = {**_OWNED_AGENT, "owner_id": OTHER_USER_ID}
        sb = MagicMock()

        def _table(name):
            if name == "agent_definitions":
                chain, _ = _mock_chain(other_owned)
                chain.maybe_single.return_value = chain
                chain.execute.return_value = MagicMock(data=other_owned)
                return chain
            return _mock_chain(None)[0]

        sb.table.side_effect = _table

        with patch(PATCH_DB, return_value=sb):
            res = client.delete(f"/api/v1/agents/{AGENT_ID}")
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/agents/:id/instance (get-or-create)
# ---------------------------------------------------------------------------


class TestGetInstance:
    def test_returns_existing_instance(self, client):
        sb = MagicMock()

        def _table(name):
            if name == "agent_definitions":
                chain, _ = _mock_chain([_OWNED_AGENT])
                return chain
            elif name == "agent_instances":
                chain, _ = _mock_chain(_INSTANCE)
                chain.maybe_single.return_value = chain
                chain.execute.return_value = MagicMock(data=_INSTANCE)
                return chain
            return _mock_chain(None)[0]

        sb.table.side_effect = _table

        with patch(PATCH_DB, return_value=sb):
            res = client.get(f"/api/v1/agents/{AGENT_ID}/instance")
        assert res.status_code == 200
        assert res.json()["id"] == INSTANCE_ID

    def test_creates_instance_when_missing(self, client):
        """
        Instance doesn't exist: first select returns None, insert runs,
        re-select returns the new instance.
        supabase.table("agent_instances") is called 3 times — use a counter.
        """
        sb = MagicMock()
        ai_calls = [0]

        def _table(name):
            if name == "agent_definitions":
                chain, _ = _mock_chain([_OWNED_AGENT])
                return chain
            elif name == "agent_instances":
                ai_calls[0] += 1
                call_num = ai_calls[0]
                if call_num == 1:
                    # First select: not found
                    chain, _ = _mock_chain(None)
                    chain.maybe_single.return_value = chain
                    chain.execute.return_value = MagicMock(data=None)
                    return chain
                elif call_num == 2:
                    # Insert
                    chain, _ = _mock_chain([_INSTANCE])
                    return chain
                else:
                    # Re-select: found
                    chain, _ = _mock_chain(_INSTANCE)
                    chain.maybe_single.return_value = chain
                    chain.execute.return_value = MagicMock(data=_INSTANCE)
                    return chain
            return _mock_chain(None)[0]

        sb.table.side_effect = _table

        with patch(PATCH_DB, return_value=sb):
            res = client.get(f"/api/v1/agents/{AGENT_ID}/instance")
        assert res.status_code == 200

    def test_404_for_inaccessible_agent(self, client):
        private_other = {**_OWNED_AGENT, "owner_id": OTHER_USER_ID, "visibility": "private"}
        sb = _make_supabase(all_agents=[private_other])
        with patch(PATCH_DB, return_value=sb):
            res = client.get(f"/api/v1/agents/{AGENT_ID}/instance")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/agents/:id/instance
# ---------------------------------------------------------------------------


class TestUpdateInstance:
    def test_updates_framework_overrides(self, client):
        updated_instance = {
            **_INSTANCE,
            "framework_overrides": {"pinned": ["fw-1"], "excluded": []},
        }
        sb = MagicMock()
        ai_calls = [0]

        def _table(name):
            if name == "agent_definitions":
                chain, _ = _mock_chain([_OWNED_AGENT])
                return chain
            elif name == "agent_instances":
                ai_calls[0] += 1
                call_num = ai_calls[0]
                if call_num == 1:
                    # get_or_create_instance select: instance found
                    chain, _ = _mock_chain(_INSTANCE)
                    chain.maybe_single.return_value = chain
                    chain.execute.return_value = MagicMock(data=_INSTANCE)
                    return chain
                else:
                    # update call
                    chain, _ = _mock_chain([updated_instance])
                    chain.execute.return_value = MagicMock(data=[updated_instance])
                    return chain
            return _mock_chain(None)[0]

        sb.table.side_effect = _table

        with patch(PATCH_DB, return_value=sb):
            res = client.patch(
                f"/api/v1/agents/{AGENT_ID}/instance",
                json={"framework_overrides": {"pinned": ["fw-1"], "excluded": []}},
            )
        assert res.status_code == 200
        assert res.json()["framework_overrides"]["pinned"] == ["fw-1"]
