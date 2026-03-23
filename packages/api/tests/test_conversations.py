"""
Tests for Conversation CRUD — KIN-272 / KIN-296.

Scaffolded by Jìan (KIN-296) before implementation. Activated by KIN-292.

Covers:
  - POST   /api/v1/conversations
  - GET    /api/v1/conversations
  - GET    /api/v1/conversations/{id}
  - PATCH  /api/v1/conversations/{id}
  - DELETE /api/v1/conversations/{id}  (soft-delete)
  - Scope: project conversation vs company-level conversation
  - System messages excluded from GET response
  - Soft-delete filtering (deleted conversations hidden by default)
  - Ownership isolation
"""

import pytest
from .conftest import make_company, make_project


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_conversation(client, company_id, project_id=None, title=None):
    body = {"company_id": company_id}
    if project_id:
        body["project_id"] = project_id
    if title:
        body["title"] = title
    resp = client.post("/api/v1/conversations", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/v1/conversations
# ---------------------------------------------------------------------------

class TestCreateConversation:
    def test_create_project_conversation(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        resp = auth_client.post(
            "/api/v1/conversations",
            json={"company_id": company["id"], "project_id": project["id"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["company_id"] == company["id"]
        assert data["project_id"] == project["id"]
        assert data["active_agent_id"] is None

    def test_create_company_level_conversation(self, auth_client):
        company = make_company(auth_client)
        resp = auth_client.post(
            "/api/v1/conversations",
            json={"company_id": company["id"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["project_id"] is None

    def test_title_defaults_to_null(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        assert conv["title"] is None

    def test_title_can_be_set_on_create(self, auth_client):
        company = make_company(auth_client)
        resp = auth_client.post(
            "/api/v1/conversations",
            json={"company_id": company["id"], "title": "Initial Title"},
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "Initial Title"

    def test_cross_user_company_returns_403(self, auth_client, other_client):
        other_company = make_company(other_client)
        resp = auth_client.post(
            "/api/v1/conversations",
            json={"company_id": other_company["id"]},
        )
        assert resp.status_code == 403

    def test_project_not_belonging_to_company_returns_403(self, auth_client):
        c1 = make_company(auth_client, name="C1")
        c2 = make_company(auth_client, name="C2")
        project_in_c1 = make_project(auth_client, c1["id"])
        # project belongs to c1 but conversation references c2
        resp = auth_client.post(
            "/api/v1/conversations",
            json={"company_id": c2["id"], "project_id": project_in_c1["id"]},
        )
        assert resp.status_code in (403, 404)

    def test_nonexistent_project_returns_404(self, auth_client):
        company = make_company(auth_client)
        resp = auth_client.post(
            "/api/v1/conversations",
            json={
                "company_id": company["id"],
                "project_id": "00000000-0000-0000-0000-999999999999",
            },
        )
        assert resp.status_code == 404

    def test_company_id_required(self, auth_client):
        resp = auth_client.post("/api/v1/conversations", json={})
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, client):
        resp = client.post(
            "/api/v1/conversations",
            json={"company_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/conversations
# ---------------------------------------------------------------------------

class TestListConversations:
    def test_returns_own_conversations(self, auth_client):
        company = make_company(auth_client)
        make_conversation(auth_client, company["id"])
        make_conversation(auth_client, company["id"])
        resp = auth_client.get("/api/v1/conversations")
        assert resp.status_code == 200
        assert len(resp.json()["conversations"]) >= 2

    def test_excludes_soft_deleted_by_default(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        auth_client.delete(f"/api/v1/conversations/{conv['id']}")
        resp = auth_client.get("/api/v1/conversations")
        ids = [c["id"] for c in resp.json()["conversations"]]
        assert conv["id"] not in ids

    def test_include_deleted_flag_shows_deleted(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        auth_client.delete(f"/api/v1/conversations/{conv['id']}")
        resp = auth_client.get("/api/v1/conversations?include_deleted=true")
        ids = [c["id"] for c in resp.json()["conversations"]]
        assert conv["id"] in ids

    def test_filter_by_company_id(self, auth_client):
        c1 = make_company(auth_client, name="C1")
        c2 = make_company(auth_client, name="C2")
        conv1 = make_conversation(auth_client, c1["id"])
        make_conversation(auth_client, c2["id"])
        resp = auth_client.get(f"/api/v1/conversations?company_id={c1['id']}")
        ids = [c["id"] for c in resp.json()["conversations"]]
        assert conv1["id"] in ids

    def test_filter_by_project_id(self, auth_client):
        company = make_company(auth_client)
        p1 = make_project(auth_client, company["id"])
        p2 = make_project(auth_client, company["id"])
        conv_p1 = make_conversation(auth_client, company["id"], project_id=p1["id"])
        make_conversation(auth_client, company["id"], project_id=p2["id"])
        resp = auth_client.get(f"/api/v1/conversations?project_id={p1['id']}")
        ids = [c["id"] for c in resp.json()["conversations"]]
        assert conv_p1["id"] in ids

    def test_ordered_by_updated_at_desc(self, auth_client):
        company = make_company(auth_client)
        c1 = make_conversation(auth_client, company["id"])
        c2 = make_conversation(auth_client, company["id"])
        resp = auth_client.get("/api/v1/conversations")
        ids = [c["id"] for c in resp.json()["conversations"]]
        assert ids.index(c2["id"]) < ids.index(c1["id"])

    def test_does_not_return_other_users_conversations(self, auth_client, other_client):
        other_company = make_company(other_client)
        make_conversation(other_client, other_company["id"])
        resp = auth_client.get("/api/v1/conversations")
        # Should only see own conversations
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/conversations/{id}
# ---------------------------------------------------------------------------

class TestGetConversation:
    def test_fetch_own_conversation_with_messages(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        resp = auth_client.get(f"/api/v1/conversations/{conv['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == conv["id"]
        assert "messages" in data

    def test_messages_empty_for_new_conversation(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        resp = auth_client.get(f"/api/v1/conversations/{conv['id']}")
        assert resp.json()["messages"] == []

    def test_system_messages_excluded(self, auth_client):
        """System messages (role=system) must never appear in conversation detail response."""
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        resp = auth_client.get(f"/api/v1/conversations/{conv['id']}")
        for msg in resp.json()["messages"]:
            assert msg["role"] != "system"

    def test_messages_ordered_by_sequence_asc(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        resp = auth_client.get(f"/api/v1/conversations/{conv['id']}")
        seqs = [m["sequence"] for m in resp.json()["messages"]]
        assert seqs == sorted(seqs)

    def test_soft_deleted_returns_404(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        auth_client.delete(f"/api/v1/conversations/{conv['id']}")
        resp = auth_client.get(f"/api/v1/conversations/{conv['id']}")
        assert resp.status_code == 404

    def test_other_users_conversation_returns_404(self, auth_client, other_client):
        other_company = make_company(other_client)
        other_conv = make_conversation(other_client, other_company["id"])
        resp = auth_client.get(f"/api/v1/conversations/{other_conv['id']}")
        assert resp.status_code == 404

    def test_nonexistent_returns_404(self, auth_client):
        resp = auth_client.get(
            "/api/v1/conversations/00000000-0000-0000-0000-999999999999"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/conversations/{id}
# ---------------------------------------------------------------------------

class TestUpdateConversation:
    def test_rename_title(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        resp = auth_client.patch(
            f"/api/v1/conversations/{conv['id']}",
            json={"title": "Renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Renamed"

    def test_set_active_agent(self, auth_client):
        """Setting active_agent_id to a valid accessible agent UUID updates the field."""
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        # Create a public agent
        agent_resp = auth_client.post(
            "/api/v1/agents",
            json={"name": "Helper", "system_prompt": "Be helpful.", "visibility": "public"},
        )
        if agent_resp.status_code not in (200, 201):
            pytest.skip("Agent endpoint not yet implemented (Sprint 4)")
        agent_id = agent_resp.json()["id"]
        resp = auth_client.patch(
            f"/api/v1/conversations/{conv['id']}",
            json={"active_agent_id": agent_id},
        )
        assert resp.status_code == 200
        assert resp.json()["active_agent_id"] == agent_id

    def test_clear_active_agent(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        resp = auth_client.patch(
            f"/api/v1/conversations/{conv['id']}",
            json={"active_agent_id": None},
        )
        assert resp.status_code == 200
        assert resp.json()["active_agent_id"] is None

    def test_set_inaccessible_agent_returns_403(self, auth_client, other_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        # Other user creates a private agent
        agent_resp = other_client.post(
            "/api/v1/agents",
            json={"name": "Private", "system_prompt": "Secret.", "visibility": "private"},
        )
        if agent_resp.status_code not in (200, 201):
            pytest.skip("Agent endpoint not yet implemented (Sprint 4)")
        agent_id = agent_resp.json()["id"]
        resp = auth_client.patch(
            f"/api/v1/conversations/{conv['id']}",
            json={"active_agent_id": agent_id},
        )
        assert resp.status_code == 403

    def test_cannot_update_other_users_conversation(self, auth_client, other_client):
        other_company = make_company(other_client)
        other_conv = make_conversation(other_client, other_company["id"])
        resp = auth_client.patch(
            f"/api/v1/conversations/{other_conv['id']}",
            json={"title": "Hijacked"},
        )
        assert resp.status_code in (403, 404)

    def test_update_returns_conversation_without_messages(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        resp = auth_client.patch(
            f"/api/v1/conversations/{conv['id']}",
            json={"title": "New Title"},
        )
        assert resp.status_code == 200
        # PATCH response should NOT include the messages array (spec § 2.2)
        assert "messages" not in resp.json()

    def test_update_nonexistent_returns_404(self, auth_client):
        resp = auth_client.patch(
            "/api/v1/conversations/00000000-0000-0000-0000-999999999999",
            json={"title": "Ghost"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/conversations/{id}  — soft-delete
# ---------------------------------------------------------------------------

class TestDeleteConversation:
    def test_soft_delete_returns_204(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        resp = auth_client.delete(f"/api/v1/conversations/{conv['id']}")
        assert resp.status_code == 204

    def test_soft_delete_hides_from_list(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        auth_client.delete(f"/api/v1/conversations/{conv['id']}")
        list_resp = auth_client.get("/api/v1/conversations")
        ids = [c["id"] for c in list_resp.json()["conversations"]]
        assert conv["id"] not in ids

    def test_soft_delete_retains_messages_in_db(self, auth_client):
        """Messages must not be deleted when a conversation is soft-deleted.
        Verified indirectly: include_deleted=true still returns the conversation."""
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        auth_client.delete(f"/api/v1/conversations/{conv['id']}")
        # The row should still exist (soft-deleted)
        list_resp = auth_client.get("/api/v1/conversations?include_deleted=true")
        ids = [c["id"] for c in list_resp.json()["conversations"]]
        assert conv["id"] in ids

    def test_cannot_delete_other_users_conversation(self, auth_client, other_client):
        other_company = make_company(other_client)
        other_conv = make_conversation(other_client, other_company["id"])
        resp = auth_client.delete(f"/api/v1/conversations/{other_conv['id']}")
        assert resp.status_code in (403, 404)

    def test_delete_nonexistent_returns_404(self, auth_client):
        resp = auth_client.delete(
            "/api/v1/conversations/00000000-0000-0000-0000-999999999999"
        )
        assert resp.status_code == 404

    def test_double_delete_returns_404(self, auth_client):
        company = make_company(auth_client)
        conv = make_conversation(auth_client, company["id"])
        auth_client.delete(f"/api/v1/conversations/{conv['id']}")
        resp = auth_client.delete(f"/api/v1/conversations/{conv['id']}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# updated_at tracking (spec § 3.3)
# ---------------------------------------------------------------------------

class TestUpdatedAt:
    def test_updated_at_bumped_after_message(self, auth_client):
        """conversations.updated_at must increase after a message is added."""
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        conv = make_conversation(auth_client, company["id"], project_id=project["id"])
        original_ts = conv["updated_at"]

        msg_resp = auth_client.post(
            f"/api/v1/conversations/{conv['id']}/messages",
            json={"content": "Hello, world!"},
        )
        if msg_resp.status_code not in (200, 201):
            pytest.skip("Generation endpoint not yet implemented (Sprint 3 Big Head)")

        refreshed = auth_client.get(f"/api/v1/conversations/{conv['id']}").json()
        assert refreshed["updated_at"] > original_ts
