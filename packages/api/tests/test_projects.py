"""
Tests for Project CRUD — KIN-263 / KIN-278.

Covers:
  - POST   /api/v1/projects
  - GET    /api/v1/projects
  - GET    /api/v1/projects/{id}
  - PATCH  /api/v1/projects/{id}
  - DELETE /api/v1/projects/{id}
  - Company ownership enforcement
  - Company reassignment preserves child data
  - Delete cascade to conversations
"""

import pytest
from .conftest import make_company, make_project


# ---------------------------------------------------------------------------
# POST /api/v1/projects
# ---------------------------------------------------------------------------

class TestCreateProject:
    def test_create_with_valid_company(self, auth_client):
        company = make_company(auth_client)
        resp = auth_client.post(
            "/api/v1/projects",
            json={"name": "Apollo", "company_id": company["id"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Apollo"
        assert data["company_id"] == company["id"]

    def test_create_with_instructions(self, auth_client):
        company = make_company(auth_client)
        resp = auth_client.post(
            "/api/v1/projects",
            json={
                "name": "Gemini",
                "company_id": company["id"],
                "instructions": "Always be concise.",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["instructions"] == "Always be concise."

    def test_create_with_cross_user_company_returns_403(self, auth_client, other_client):
        other_company = make_company(other_client, name="OtherCo")
        resp = auth_client.post(
            "/api/v1/projects",
            json={"name": "Steal", "company_id": other_company["id"]},
        )
        assert resp.status_code == 403

    def test_create_with_nonexistent_company_returns_404(self, auth_client):
        resp = auth_client.post(
            "/api/v1/projects",
            json={
                "name": "Ghost",
                "company_id": "00000000-0000-0000-0000-999999999999",
            },
        )
        assert resp.status_code in (403, 404)

    def test_name_required(self, auth_client):
        company = make_company(auth_client)
        resp = auth_client.post(
            "/api/v1/projects",
            json={"company_id": company["id"]},
        )
        assert resp.status_code == 422

    def test_company_id_required(self, auth_client):
        resp = auth_client.post("/api/v1/projects", json={"name": "No Company"})
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, client):
        resp = client.post(
            "/api/v1/projects",
            json={"name": "Anon", "company_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/projects
# ---------------------------------------------------------------------------

class TestListProjects:
    def test_returns_own_projects(self, auth_client):
        company = make_company(auth_client)
        make_project(auth_client, company["id"], name="Alpha")
        make_project(auth_client, company["id"], name="Beta")
        resp = auth_client.get("/api/v1/projects")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "Alpha" in names
        assert "Beta" in names

    def test_filter_by_company_id(self, auth_client):
        c1 = make_company(auth_client, name="C1")
        c2 = make_company(auth_client, name="C2")
        make_project(auth_client, c1["id"], name="In C1")
        make_project(auth_client, c2["id"], name="In C2")

        resp = auth_client.get(f"/api/v1/projects?company_id={c1['id']}")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "In C1" in names
        assert "In C2" not in names

    def test_does_not_return_other_users_projects(self, auth_client, other_client):
        other_company = make_company(other_client)
        make_project(other_client, other_company["id"], name="OtherProject")
        resp = auth_client.get("/api/v1/projects")
        names = [p["name"] for p in resp.json()]
        assert "OtherProject" not in names

    def test_ordered_by_updated_at_desc(self, auth_client):
        company = make_company(auth_client)
        p1 = make_project(auth_client, company["id"], name="First")
        p2 = make_project(auth_client, company["id"], name="Second")
        resp = auth_client.get("/api/v1/projects")
        ids = [p["id"] for p in resp.json()]
        assert ids.index(p2["id"]) < ids.index(p1["id"])


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{id}
# ---------------------------------------------------------------------------

class TestGetProject:
    def test_fetch_own_project(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"], name="Fetch Me")
        resp = auth_client.get(f"/api/v1/projects/{project['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fetch Me"

    def test_fetch_other_users_project_returns_404(self, auth_client, other_client):
        other_company = make_company(other_client)
        other_project = make_project(other_client, other_company["id"])
        resp = auth_client.get(f"/api/v1/projects/{other_project['id']}")
        assert resp.status_code == 404

    def test_fetch_nonexistent_returns_404(self, auth_client):
        resp = auth_client.get("/api/v1/projects/00000000-0000-0000-0000-999999999999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/projects/{id}
# ---------------------------------------------------------------------------

class TestUpdateProject:
    def test_update_name(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"], name="Old")
        resp = auth_client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"name": "New"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    def test_update_instructions(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        resp = auth_client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"instructions": "Be brief."},
        )
        assert resp.status_code == 200
        assert resp.json()["instructions"] == "Be brief."

    def test_company_reassignment_succeeds(self, auth_client):
        c1 = make_company(auth_client, name="Source")
        c2 = make_company(auth_client, name="Target")
        project = make_project(auth_client, c1["id"])
        resp = auth_client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"company_id": c2["id"]},
        )
        assert resp.status_code == 200
        assert resp.json()["company_id"] == c2["id"]

    def test_company_reassignment_preserves_child_data(self, auth_client):
        """After reassignment, child conversations should remain on the project."""
        c1 = make_company(auth_client, name="Source")
        c2 = make_company(auth_client, name="Target")
        project = make_project(auth_client, c1["id"])

        # Create a conversation in the project
        conv_resp = auth_client.post(
            "/api/v1/conversations",
            json={"project_id": project["id"], "title": "Orphan Check"},
        )
        if conv_resp.status_code in (201, 200):
            conv_id = conv_resp.json()["id"]
            # Reassign project to a different company
            auth_client.patch(
                f"/api/v1/projects/{project['id']}",
                json={"company_id": c2["id"]},
            )
            # Conversation should still be accessible
            get_conv = auth_client.get(f"/api/v1/conversations/{conv_id}")
            assert get_conv.status_code == 200
        else:
            pytest.skip("Conversation endpoint not yet implemented (Sprint 3)")

    def test_reassign_to_cross_user_company_returns_403(self, auth_client, other_client):
        c1 = make_company(auth_client)
        other_company = make_company(other_client, name="OtherCo")
        project = make_project(auth_client, c1["id"])
        resp = auth_client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"company_id": other_company["id"]},
        )
        assert resp.status_code == 403

    def test_cannot_update_other_users_project(self, auth_client, other_client):
        other_company = make_company(other_client)
        other_project = make_project(other_client, other_company["id"])
        resp = auth_client.patch(
            f"/api/v1/projects/{other_project['id']}",
            json={"name": "Hijacked"},
        )
        assert resp.status_code in (403, 404)

    def test_update_nonexistent_returns_404(self, auth_client):
        resp = auth_client.patch(
            "/api/v1/projects/00000000-0000-0000-0000-999999999999",
            json={"name": "Ghost"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/projects/{id}
# ---------------------------------------------------------------------------

class TestDeleteProject:
    def test_delete_own_project(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"], name="Bye")
        resp = auth_client.delete(f"/api/v1/projects/{project['id']}")
        assert resp.status_code in (200, 204)
        get_resp = auth_client.get(f"/api/v1/projects/{project['id']}")
        assert get_resp.status_code == 404

    def test_delete_cascades_to_conversations(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])

        conv_resp = auth_client.post(
            "/api/v1/conversations",
            json={"project_id": project["id"], "title": "Cascade Test"},
        )
        if conv_resp.status_code in (201, 200):
            conv_id = conv_resp.json()["id"]
            auth_client.delete(f"/api/v1/projects/{project['id']}")
            get_conv = auth_client.get(f"/api/v1/conversations/{conv_id}")
            assert get_conv.status_code == 404
        else:
            pytest.skip("Conversation endpoint not yet implemented (Sprint 3)")

    def test_cannot_delete_other_users_project(self, auth_client, other_client):
        other_company = make_company(other_client)
        other_project = make_project(other_client, other_company["id"])
        resp = auth_client.delete(f"/api/v1/projects/{other_project['id']}")
        assert resp.status_code in (403, 404)

    def test_delete_nonexistent_returns_404(self, auth_client):
        resp = auth_client.delete("/api/v1/projects/00000000-0000-0000-0000-999999999999")
        assert resp.status_code == 404
