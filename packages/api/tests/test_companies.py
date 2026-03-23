"""Route tests for Company CRUD — KIN-278 (KIN-262)."""
from __future__ import annotations

import pytest

from tests.conftest import TEST_COMPANY_ID, TEST_USER_ID, ok, empty, seq


COMPANY_ROW = {
    "id": TEST_COMPANY_ID,
    "user_id": TEST_USER_ID,
    "name": "Acme Corp",
    "description": "Widget makers",
}


class TestCreateCompany:
    def test_success(self, client, sb):
        sb.execute.return_value = ok([COMPANY_ROW])
        r = client.post("/api/v1/companies", json={"name": "Acme Corp", "description": "Widget makers"})
        assert r.status_code == 201
        assert r.json()["name"] == "Acme Corp"

    def test_name_required(self, client, sb):
        r = client.post("/api/v1/companies", json={"description": "no name"})
        assert r.status_code == 422

    def test_empty_name_returns_422(self, client, sb):
        r = client.post("/api/v1/companies", json={"name": "   "})
        assert r.status_code == 422

    def test_insert_failure_returns_400(self, client, sb):
        sb.execute.return_value = empty()
        r = client.post("/api/v1/companies", json={"name": "Acme"})
        assert r.status_code == 400


class TestListCompanies:
    def test_returns_list(self, client, sb):
        sb.execute.return_value = ok([COMPANY_ROW])
        r = client.get("/api/v1/companies")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_empty_list(self, client, sb):
        sb.execute.return_value = ok([])
        r = client.get("/api/v1/companies")
        assert r.status_code == 200
        assert r.json() == []


class TestGetCompany:
    def test_found(self, client, sb):
        sb.execute.return_value = ok(COMPANY_ROW)
        r = client.get(f"/api/v1/companies/{TEST_COMPANY_ID}")
        assert r.status_code == 200
        assert r.json()["id"] == TEST_COMPANY_ID

    def test_not_found(self, client, sb):
        sb.execute.return_value = empty()
        r = client.get(f"/api/v1/companies/{TEST_COMPANY_ID}")
        assert r.status_code == 404


class TestUpdateCompany:
    def test_success(self, client, sb):
        updated = {**COMPANY_ROW, "name": "New Name"}
        seq(sb, ok(COMPANY_ROW), ok([updated]))
        r = client.patch(f"/api/v1/companies/{TEST_COMPANY_ID}", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_not_found(self, client, sb):
        seq(sb, empty())
        r = client.patch(f"/api/v1/companies/{TEST_COMPANY_ID}", json={"name": "X"})
        assert r.status_code == 404

    def test_description_too_long(self, client, sb):
        r = client.patch(f"/api/v1/companies/{TEST_COMPANY_ID}", json={"description": "x" * 1001})
        assert r.status_code == 422


class TestDeleteCompany:
    def test_success(self, client, sb):
        seq(sb, ok(COMPANY_ROW), ok([]))
        r = client.delete(f"/api/v1/companies/{TEST_COMPANY_ID}")
        assert r.status_code == 204

    def test_not_found(self, client, sb):
        seq(sb, empty())
        r = client.delete(f"/api/v1/companies/{TEST_COMPANY_ID}")
        assert r.status_code == 404
