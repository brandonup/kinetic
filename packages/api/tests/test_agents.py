"""
Tests for AgentDefinition CRUD + AgentInstance lifecycle + Agent Invocation — KIN-297.

Scaffolded by Jìan (KIN-297). Activated by KIN-293 once Sprint 4 ships.

Covers:
  KIN-287 — AgentDefinition CRUD (POST/GET/PATCH/DELETE + visibility + constraints)
  KIN-288 — AgentInstance auto-create on first invocation (get-or-create semantics)
  KIN-289 — Agent invocation + switch in conversations

Spec ref:  docs/specs/agents.md
Schema:    docs/db-schema-spec.md §8 (agent_definitions), §9 (agent_instances)
"""

import pytest
from .conftest import make_company, make_project

SKIP_REASON = "Blocked — waiting for KIN-287/KIN-288/KIN-289 (Sprint 4 Dinesh)"
SKIP_INVOCATION = "Blocked — waiting for KIN-289 (Sprint 4 agent invocation) + KIN-276 (generation)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_agent(client, name="Test Agent", instructions="Be helpful.", visibility="private"):
    resp = client.post(
        "/api/v1/agents",
        json={"name": name, "instructions": instructions, "type": "custom", "visibility": visibility},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/v1/agents — create AgentDefinition
# ---------------------------------------------------------------------------

class TestCreateAgentDefinition:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_create_private_agent(self, auth_client):
        """POST creates a private agent owned by the authenticated user."""
        resp = auth_client.post(
            "/api/v1/agents",
            json={"name": "My Agent", "instructions": "Be concise.", "type": "custom", "visibility": "private"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["visibility"] == "private"
        assert data["owner_id"] == auth_client.user_id

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_create_public_agent(self, auth_client):
        """Can create a public agent when instructions are non-empty."""
        resp = auth_client.post(
            "/api/v1/agents",
            json={"name": "Public Agent", "instructions": "Help everyone.", "type": "custom", "visibility": "public"},
        )
        assert resp.status_code == 201
        assert resp.json()["visibility"] == "public"

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_create_public_without_instructions_rejected(self, auth_client):
        """Visibility = public requires non-empty instructions."""
        resp = auth_client.post(
            "/api/v1/agents",
            json={"name": "Empty Agent", "instructions": "", "type": "custom", "visibility": "public"},
        )
        assert resp.status_code in (400, 422)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_name_required(self, auth_client):
        resp = auth_client.post(
            "/api/v1/agents",
            json={"instructions": "Hello.", "type": "custom", "visibility": "private"},
        )
        assert resp.status_code == 422

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_name_unique_per_owner(self, auth_client):
        """Two agents with the same name owned by the same user must be rejected."""
        make_agent(auth_client, name="Duplicate")
        resp = auth_client.post(
            "/api/v1/agents",
            json={"name": "Duplicate", "instructions": "Second.", "type": "custom", "visibility": "private"},
        )
        assert resp.status_code in (400, 409)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_same_name_allowed_for_different_owners(self, auth_client, other_client):
        """Two different owners can each have an agent named 'Helper'."""
        make_agent(auth_client, name="Helper")
        resp = other_client.post(
            "/api/v1/agents",
            json={"name": "Helper", "instructions": "Helpful.", "type": "custom", "visibility": "private"},
        )
        assert resp.status_code in (200, 201)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_default_mcp_enabled_is_false(self, auth_client):
        agent = make_agent(auth_client)
        assert agent["mcp_enabled"] is False

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_unauthenticated_returns_401(self, client):
        resp = client.post(
            "/api/v1/agents",
            json={"name": "Ghost", "instructions": "...", "type": "custom", "visibility": "private"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/agents — list
# ---------------------------------------------------------------------------

class TestListAgents:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_returns_own_agents(self, auth_client):
        make_agent(auth_client, name="My1")
        make_agent(auth_client, name="My2")
        resp = auth_client.get("/api/v1/agents")
        assert resp.status_code == 200
        names = [a["name"] for a in resp.json()["agents"]]
        assert "My1" in names and "My2" in names

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_returns_other_users_public_agents(self, auth_client, other_client):
        make_agent(other_client, name="OtherPublic", visibility="public")
        resp = auth_client.get("/api/v1/agents")
        names = [a["name"] for a in resp.json()["agents"]]
        assert "OtherPublic" in names

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_does_not_return_other_users_private_agents(self, auth_client, other_client):
        make_agent(other_client, name="OtherPrivate", visibility="private")
        resp = auth_client.get("/api/v1/agents")
        names = [a["name"] for a in resp.json()["agents"]]
        assert "OtherPrivate" not in names

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_agents_without_instructions_shown_but_flagged(self, auth_client):
        """Agents with empty instructions appear in list but are non-invocable (flagged)."""
        ...


# ---------------------------------------------------------------------------
# GET /api/v1/agents/:id — fetch single
# ---------------------------------------------------------------------------

class TestGetAgentDefinition:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_owner_can_fetch_private_agent(self, auth_client):
        agent = make_agent(auth_client)
        resp = auth_client.get(f"/api/v1/agents/{agent['id']}")
        assert resp.status_code == 200

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_any_user_can_fetch_public_agent(self, auth_client, other_client):
        agent = make_agent(other_client, visibility="public")
        resp = auth_client.get(f"/api/v1/agents/{agent['id']}")
        assert resp.status_code == 200

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_private_agent_returns_404_to_other_user(self, auth_client, other_client):
        agent = make_agent(other_client, visibility="private")
        resp = auth_client.get(f"/api/v1/agents/{agent['id']}")
        assert resp.status_code == 404

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_nonexistent_returns_404(self, auth_client):
        resp = auth_client.get("/api/v1/agents/00000000-0000-0000-0000-999999999999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/agents/:id — update
# ---------------------------------------------------------------------------

class TestUpdateAgentDefinition:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_owner_can_update_name(self, auth_client):
        agent = make_agent(auth_client)
        resp = auth_client.patch(f"/api/v1/agents/{agent['id']}", json={"name": "Renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_owner_can_update_instructions(self, auth_client):
        agent = make_agent(auth_client)
        resp = auth_client.patch(
            f"/api/v1/agents/{agent['id']}",
            json={"instructions": "New instructions."},
        )
        assert resp.status_code == 200

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_update_propagates_immediately_to_all_invokers(self, auth_client, other_client):
        """After owner updates instructions, other user's next context assembly uses new instructions."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_cannot_set_empty_instructions_when_public(self, auth_client):
        agent = make_agent(auth_client, visibility="public")
        resp = auth_client.patch(
            f"/api/v1/agents/{agent['id']}",
            json={"instructions": ""},
        )
        assert resp.status_code in (400, 422)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_non_owner_cannot_update(self, auth_client, other_client):
        agent = make_agent(other_client, visibility="public")
        resp = auth_client.patch(f"/api/v1/agents/{agent['id']}", json={"name": "Hijacked"})
        assert resp.status_code in (403, 404)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_set_visibility_to_public_requires_instructions(self, auth_client):
        agent = make_agent(auth_client, instructions="Non-empty.")
        # Clear instructions first, then attempt to set public
        auth_client.patch(f"/api/v1/agents/{agent['id']}", json={"instructions": None})
        resp = auth_client.patch(f"/api/v1/agents/{agent['id']}", json={"visibility": "public"})
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# DELETE /api/v1/agents/:id
# ---------------------------------------------------------------------------

class TestDeleteAgentDefinition:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_owner_can_delete_private_agent(self, auth_client):
        agent = make_agent(auth_client)
        resp = auth_client.delete(f"/api/v1/agents/{agent['id']}")
        assert resp.status_code == 204

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_delete_removes_agent_from_list(self, auth_client):
        agent = make_agent(auth_client)
        auth_client.delete(f"/api/v1/agents/{agent['id']}")
        resp = auth_client.get("/api/v1/agents")
        ids = [a["id"] for a in resp.json()["agents"]]
        assert agent["id"] not in ids

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_delete_public_agent_blocked_when_has_invokers(self, auth_client, other_client):
        """Public agent with active invokers cannot be deleted until transferred/privatised."""
        agent = make_agent(auth_client, visibility="public")
        # other_client invokes the agent to create an AgentInstance
        other_client.get(f"/api/v1/agents/{agent['id']}/instance")
        resp = auth_client.delete(f"/api/v1/agents/{agent['id']}")
        assert resp.status_code in (400, 409)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_non_owner_cannot_delete(self, auth_client, other_client):
        agent = make_agent(other_client, visibility="public")
        resp = auth_client.delete(f"/api/v1/agents/{agent['id']}")
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# AgentInstance — GET /api/v1/agents/:id/instance (get-or-create)
# ---------------------------------------------------------------------------

class TestAgentInstanceGetOrCreate:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_first_invocation_creates_instance(self, auth_client, other_client):
        agent = make_agent(other_client, visibility="public")
        resp = auth_client.get(f"/api/v1/agents/{agent['id']}/instance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_definition_id"] == agent["id"]
        assert data["active_memory"] is None

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_second_invocation_returns_same_instance(self, auth_client, other_client):
        agent = make_agent(other_client, visibility="public")
        r1 = auth_client.get(f"/api/v1/agents/{agent['id']}/instance")
        r2 = auth_client.get(f"/api/v1/agents/{agent['id']}/instance")
        assert r1.json()["id"] == r2.json()["id"]

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_concurrent_first_invocations_create_single_instance(self, auth_client, other_client):
        """Race condition: two concurrent GET-or-creates must not produce duplicate instances."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_instance_unique_per_user_per_agent(self, auth_client, other_client):
        """user1 and user2 each get their own AgentInstance for the same AgentDefinition."""
        agent = make_agent(auth_client, visibility="public")
        i1 = auth_client.get(f"/api/v1/agents/{agent['id']}/instance").json()
        i2 = other_client.get(f"/api/v1/agents/{agent['id']}/instance").json()
        assert i1["id"] != i2["id"]

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_instance_not_accessible_by_owner_of_definition(self, auth_client, other_client):
        """AgentDefinition owner cannot see another user's AgentInstance data."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_cannot_invoke_private_agent_of_other_user(self, auth_client, other_client):
        agent = make_agent(other_client, visibility="private")
        resp = auth_client.get(f"/api/v1/agents/{agent['id']}/instance")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# AgentInstance — PATCH /api/v1/agents/:id/instance
# ---------------------------------------------------------------------------

class TestAgentInstanceUpdate:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_update_active_memory(self, auth_client, other_client):
        agent = make_agent(other_client, visibility="public")
        auth_client.get(f"/api/v1/agents/{agent['id']}/instance")  # create
        resp = auth_client.patch(
            f"/api/v1/agents/{agent['id']}/instance",
            json={"active_memory": "User prefers bullet points."},
        )
        assert resp.status_code == 200
        assert resp.json()["active_memory"] == "User prefers bullet points."

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_active_memory_cap_500_tokens(self, auth_client, other_client):
        """Writing active_memory that exceeds 500 tokens must return 400 with clear message."""
        agent = make_agent(other_client, visibility="public")
        auth_client.get(f"/api/v1/agents/{agent['id']}/instance")
        long_memory = "A " * 600  # ~600 tokens
        resp = auth_client.patch(
            f"/api/v1/agents/{agent['id']}/instance",
            json={"active_memory": long_memory},
        )
        assert resp.status_code == 400
        assert "token" in resp.json()["error"]["message"].lower()

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_clear_active_memory(self, auth_client, other_client):
        agent = make_agent(other_client, visibility="public")
        auth_client.get(f"/api/v1/agents/{agent['id']}/instance")
        auth_client.patch(
            f"/api/v1/agents/{agent['id']}/instance",
            json={"active_memory": "Something."},
        )
        resp = auth_client.patch(
            f"/api/v1/agents/{agent['id']}/instance",
            json={"active_memory": None},
        )
        assert resp.status_code == 200
        assert resp.json()["active_memory"] is None

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_update_framework_overrides(self, auth_client, other_client):
        agent = make_agent(other_client, visibility="public")
        auth_client.get(f"/api/v1/agents/{agent['id']}/instance")
        resp = auth_client.patch(
            f"/api/v1/agents/{agent['id']}/instance",
            json={"framework_overrides": {"pinned": ["fw-1"], "excluded": ["fw-2"]}},
        )
        assert resp.status_code == 200
        overrides = resp.json()["framework_overrides"]
        assert "fw-1" in overrides["pinned"]
        assert "fw-2" in overrides["excluded"]


# ---------------------------------------------------------------------------
# Framework CRUD — /api/v1/agents/:id/frameworks
# ---------------------------------------------------------------------------

class TestFrameworkCRUD:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_create_single_framework(self, auth_client):
        agent = make_agent(auth_client)
        resp = auth_client.post(
            f"/api/v1/agents/{agent['id']}/frameworks",
            json={
                "framework_id": "coordination-tax",
                "name": "Coordination Tax Diagnostic",
                "when_to_apply": ["team is slow", "meetings overrunning"],
                "principles": ["Reduce unnecessary coordination"],
                "confidence": "high",
                "origin": "extracted",
            },
        )
        assert resp.status_code == 201

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_framework_id_unique_per_agent(self, auth_client):
        agent = make_agent(auth_client)
        fw_body = {
            "framework_id": "dup-fw",
            "name": "Dup FW",
            "when_to_apply": ["test"],
            "principles": ["test"],
            "confidence": "medium",
            "origin": "manual",
        }
        auth_client.post(f"/api/v1/agents/{agent['id']}/frameworks", json=fw_body)
        resp = auth_client.post(f"/api/v1/agents/{agent['id']}/frameworks", json=fw_body)
        assert resp.status_code in (400, 409)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_list_frameworks_for_agent(self, auth_client):
        agent = make_agent(auth_client)
        auth_client.post(
            f"/api/v1/agents/{agent['id']}/frameworks",
            json={
                "framework_id": "fw-1",
                "name": "FW 1",
                "when_to_apply": ["test"],
                "principles": ["test"],
                "confidence": "high",
                "origin": "manual",
            },
        )
        resp = auth_client.get(f"/api/v1/agents/{agent['id']}/frameworks")
        assert resp.status_code == 200
        ids = [fw["framework_id"] for fw in resp.json()["frameworks"]]
        assert "fw-1" in ids

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_non_owner_cannot_create_framework(self, auth_client, other_client):
        agent = make_agent(auth_client)
        resp = other_client.post(
            f"/api/v1/agents/{agent['id']}/frameworks",
            json={"framework_id": "hack", "name": "Hack", "when_to_apply": ["x"], "principles": ["x"],
                  "confidence": "low", "origin": "manual"},
        )
        assert resp.status_code in (403, 404)


class TestFrameworkBulkUpload:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_upload_adds_new_frameworks(self, auth_client):
        """JSON upload adds frameworks with new framework_id values."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_upload_updates_existing_framework_by_id(self, auth_client):
        """Frameworks with matching framework_id are updated in place."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_upload_retains_frameworks_not_in_file(self, auth_client):
        """Frameworks absent from the upload JSON are NOT deleted."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_upload_returns_import_summary(self, auth_client):
        """Response includes imported/updated/skipped/errors counts."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_invalid_entries_skipped_valid_entries_imported(self, auth_client):
        """Partial import: invalid rows in JSON skipped, valid rows imported."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_missing_required_fields_listed_in_errors(self, auth_client):
        """Upload errors array includes per-framework reason for skipped entries."""
        ...


# ---------------------------------------------------------------------------
# Agent invocation in conversations (KIN-289)
# ---------------------------------------------------------------------------

class TestAgentInvocationInConversation:
    @pytest.mark.skip(reason=SKIP_INVOCATION)
    def test_set_active_agent_on_conversation(self, auth_client):
        """PATCH /conversations/{id} with active_agent_id invokes the agent."""
        ...

    @pytest.mark.skip(reason=SKIP_INVOCATION)
    def test_private_agent_invocable_by_owner(self, auth_client):
        """Owner can invoke their own private agent in a conversation."""
        ...

    @pytest.mark.skip(reason=SKIP_INVOCATION)
    def test_private_agent_of_other_user_not_invocable(self, auth_client, other_client):
        """Cannot set active_agent_id to another user's private agent — returns 403."""
        ...

    @pytest.mark.skip(reason=SKIP_INVOCATION)
    def test_public_agent_invocable_by_any_user(self, auth_client, other_client):
        """Any user can invoke a public agent in their conversation."""
        ...

    @pytest.mark.skip(reason=SKIP_INVOCATION)
    def test_agent_instance_created_on_first_invocation_in_conversation(self, auth_client, other_client):
        """When a user sets active_agent_id for the first time, AgentInstance is auto-created."""
        ...

    @pytest.mark.skip(reason=SKIP_INVOCATION)
    def test_deactivate_agent_by_setting_null(self, auth_client):
        """PATCH active_agent_id=null deactivates the agent."""
        ...

    @pytest.mark.skip(reason=SKIP_INVOCATION)
    def test_switch_agent_mid_conversation_preserves_history(self, auth_client, other_client):
        """Switching agents: full message history retained, prior messages keep original agent_definition_id."""
        ...

    @pytest.mark.skip(reason=SKIP_INVOCATION)
    def test_each_message_tagged_with_active_agent_id(self, auth_client):
        """Assistant messages generated while agent is active have agent_definition_id set."""
        ...

    @pytest.mark.skip(reason=SKIP_INVOCATION)
    def test_messages_before_agent_activation_have_null_agent_id(self, auth_client):
        """Messages sent before agent was invoked retain agent_definition_id=null."""
        ...

    @pytest.mark.skip(reason=SKIP_INVOCATION)
    def test_only_one_agent_active_at_a_time(self, auth_client):
        """Setting a new active_agent_id replaces the previous one (not additive)."""
        ...

    @pytest.mark.skip(reason=SKIP_INVOCATION)
    def test_agent_without_instructions_cannot_be_invoked(self, auth_client):
        """Attempting to invoke an agent with empty instructions returns 400."""
        ...
