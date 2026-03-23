"""Route tests for Project CRUD — KIN-278 (KIN-263)."""
from __future__ import annotations

import pytest

from tests.conftest import TEST_COMPANY_ID, TEST_PROJECT_ID, TEST_USER_ID, ok, empty, seq


PROJECT_ROW = {
    "id": TEST_PROJECT_ID,
    "user_id": TEST_USER_ID,
    "company_id": TEST_COMPANY_ID,
    "name": "Atlas",
    "instructions": "Use TDD.",
}

COMPANY_ROW = {"id": TEST_COMPANY_ID, "user_id": TEST_USER_ID, "name": "Acme"}


class TestCreateProject:
    def test_success(self, client, sb):
        seq(sb, ok(COMPANY_ROW), ok([PROJECT_ROW]))
        r = client.post(
            "/api/v1/projects",
            json={"name": "Atlas", "company_id": TEST_COMPANY_ID},
        )
        assert r.status_code == 201
        assert r.json()["name"] == "Atlas"

    def test_wrong_company_returns_403(self, client, sb):
        seq(sb, empty())  # company ownership check fails
        r = client.post(
            "/api/v1/projects",
            json={"name": "Atlas", "company_id": TEST_COMPANY_ID},
        )
        assert r.status_code == 403

    def test_name_required(self, client, sb):
        r = client.post("/api/v1/projects", json={"company_id": TEST_COMPANY_ID})
        assert r.status_code == 422


class TestListProjects:
    def test_returns_list(self, client, sb):
        sb.execute.return_value = ok([PROJECT_ROW])
        r = client.get("/api/v1/projects")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_filter_by_company(self, client, sb):
        sb.execute.return_value = ok([PROJECT_ROW])
        r = client.get(f"/api/v1/projects?company_id={TEST_COMPANY_ID}")
        assert r.status_code == 200


class TestGetProject:
    def test_found(self, client, sb):
        sb.execute.return_value = ok(PROJECT_ROW)
        r = client.get(f"/api/v1/projects/{TEST_PROJECT_ID}")
        assert r.status_code == 200
        assert r.json()["id"] == TEST_PROJECT_ID

    def test_not_found(self, client, sb):
        sb.execute.return_value = empty()
        r = client.get(f"/api/v1/projects/{TEST_PROJECT_ID}")
        assert r.status_code == 404


class TestUpdateProject:
    def test_update_instructions(self, client, sb):
        updated = {**PROJECT_ROW, "instructions": "New instructions"}
        seq(sb, ok(PROJECT_ROW), ok([updated]))
        r = client.patch(
            f"/api/v1/projects/{TEST_PROJECT_ID}",
            json={"instructions": "New instructions"},
        )
        assert r.status_code == 200

    def test_not_found(self, client, sb):
        seq(sb, empty())
        r = client.patch(f"/api/v1/projects/{TEST_PROJECT_ID}", json={"name": "X"})
        assert r.status_code == 404


class TestDeleteProject:
    def test_success(self, client, sb):
        seq(sb, ok(PROJECT_ROW), ok([]))
        r = client.delete(f"/api/v1/projects/{TEST_PROJECT_ID}")
        assert r.status_code == 204

    def test_not_found(self, client, sb):
        seq(sb, empty())
        r = client.delete(f"/api/v1/projects/{TEST_PROJECT_ID}")
        assert r.status_code == 404
