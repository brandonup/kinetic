"""
Tests for Company CRUD — KIN-262 / KIN-278.

Covers:
  - POST   /api/v1/companies
  - GET    /api/v1/companies
  - GET    /api/v1/companies/{id}
  - PATCH  /api/v1/companies/{id}
  - DELETE /api/v1/companies/{id}
  - Delete cascade to projects
  - Ownership isolation between users
"""

import pytest
from .conftest import make_company, make_project


# ---------------------------------------------------------------------------
# POST /api/v1/companies
# ---------------------------------------------------------------------------

class TestCreateCompany:
    def test_create_minimal(self, auth_client):
        resp = auth_client.post("/api/v1/companies", json={"name": "Acme"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Acme"
        assert "id" in data

    def test_create_with_description(self, auth_client):
        resp = auth_client.post(
            "/api/v1/companies",
            json={"name": "Globex", "description": "A nuclear plant."},
        )
        assert resp.status_code == 201
        assert resp.json()["description"] == "A nuclear plant."

    def test_name_required(self, auth_client):
        resp = auth_client.post("/api/v1/companies", json={"description": "No name."})
        assert resp.status_code == 422

    def test_description_at_limit_accepted(self, auth_client):
        resp = auth_client.post(
            "/api/v1/companies",
            json={"name": "Limit Co", "description": "x" * 1000},
        )
        assert resp.status_code == 201

    def test_description_over_limit_rejected(self, auth_client):
        resp = auth_client.post(
            "/api/v1/companies",
            json={"name": "Over Co", "description": "x" * 1001},
        )
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, client):
        resp = client.post("/api/v1/companies", json={"name": "Anon"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/companies
# ---------------------------------------------------------------------------

class TestListCompanies:
    def test_returns_own_companies(self, auth_client):
        make_company(auth_client, name="Alpha")
        make_company(auth_client, name="Beta")
        resp = auth_client.get("/api/v1/companies")
        assert resp.status_code == 200
        names = [c["name"] for c in resp.json()]
        assert "Alpha" in names
        assert "Beta" in names

    def test_does_not_return_other_users_companies(self, auth_client, other_client):
        make_company(other_client, name="OtherCorp")
        resp = auth_client.get("/api/v1/companies")
        names = [c["name"] for c in resp.json()]
        assert "OtherCorp" not in names

    def test_ordered_by_updated_at_desc(self, auth_client):
        c1 = make_company(auth_client, name="First")
        c2 = make_company(auth_client, name="Second")
        resp = auth_client.get("/api/v1/companies")
        ids = [c["id"] for c in resp.json()]
        # Most recently created/updated should come first
        assert ids.index(c2["id"]) < ids.index(c1["id"])

    def test_empty_list_returns_empty_array(self, auth_client):
        resp = auth_client.get("/api/v1/companies")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# GET /api/v1/companies/{id}
# ---------------------------------------------------------------------------

class TestGetCompany:
    def test_fetch_own_company(self, auth_client):
        company = make_company(auth_client, name="Fetch Me")
        resp = auth_client.get(f"/api/v1/companies/{company['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fetch Me"

    def test_fetch_other_users_company_returns_404(self, auth_client, other_client):
        company = make_company(other_client, name="Private Corp")
        resp = auth_client.get(f"/api/v1/companies/{company['id']}")
        assert resp.status_code == 404

    def test_fetch_nonexistent_returns_404(self, auth_client):
        resp = auth_client.get("/api/v1/companies/00000000-0000-0000-0000-999999999999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/companies/{id}
# ---------------------------------------------------------------------------

class TestUpdateCompany:
    def test_update_name(self, auth_client):
        company = make_company(auth_client, name="Old Name")
        resp = auth_client.patch(
            f"/api/v1/companies/{company['id']}",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_update_description(self, auth_client):
        company = make_company(auth_client)
        resp = auth_client.patch(
            f"/api/v1/companies/{company['id']}",
            json={"description": "Updated desc."},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated desc."

    def test_cannot_update_other_users_company(self, auth_client, other_client):
        company = make_company(other_client, name="OtherCo")
        resp = auth_client.patch(
            f"/api/v1/companies/{company['id']}",
            json={"name": "Hijacked"},
        )
        assert resp.status_code in (403, 404)

    def test_update_nonexistent_returns_404(self, auth_client):
        resp = auth_client.patch(
            "/api/v1/companies/00000000-0000-0000-0000-999999999999",
            json={"name": "Ghost"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/companies/{id}
# ---------------------------------------------------------------------------

class TestDeleteCompany:
    def test_delete_own_company(self, auth_client):
        company = make_company(auth_client, name="To Delete")
        resp = auth_client.delete(f"/api/v1/companies/{company['id']}")
        assert resp.status_code in (200, 204)
        # Confirm gone
        get_resp = auth_client.get(f"/api/v1/companies/{company['id']}")
        assert get_resp.status_code == 404

    def test_delete_cascades_to_projects(self, auth_client):
        company = make_company(auth_client, name="Parent")
        project = make_project(auth_client, company["id"], name="Child Project")

        auth_client.delete(f"/api/v1/companies/{company['id']}")

        # Project should be gone
        proj_resp = auth_client.get(f"/api/v1/projects/{project['id']}")
        assert proj_resp.status_code == 404

    def test_cannot_delete_other_users_company(self, auth_client, other_client):
        company = make_company(other_client, name="Protected")
        resp = auth_client.delete(f"/api/v1/companies/{company['id']}")
        assert resp.status_code in (403, 404)

    def test_delete_nonexistent_returns_404(self, auth_client):
        resp = auth_client.delete("/api/v1/companies/00000000-0000-0000-0000-999999999999")
        assert resp.status_code == 404
