"""
Tests for KIN-262: Company CRUD

Covers:
  - Create company (TestCreateCompany)
  - List companies (TestListCompanies)
  - Get single company (TestGetCompany)
  - Update company (TestUpdateCompany)
  - Delete company (TestDeleteCompany)

All Supabase calls are mocked. Uses client fixture from conftest.py.
Schema ref: docs/db-schema-spec.md §3 (companies)
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

TEST_COMPANY_ID = str(uuid4())
PATCH_TARGET = "app.api.routes.companies.get_supabase_client"


def _company_row(
    company_id: str = TEST_COMPANY_ID,
    name: str = "Acme Corp",
    description: str = "A test company",
) -> dict:
    return {
        "id": company_id,
        "user_id": str(uuid4()),
        "name": name,
        "description": description,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Task 1: Create company
# ---------------------------------------------------------------------------


class TestCreateCompany:
    def test_create_returns_company(self, client):
        row = _company_row()
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[row]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/companies", json={"name": "Acme Corp", "description": "A test company"}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Acme Corp"
        assert data["description"] == "A test company"

    def test_create_name_only(self, client):
        row = _company_row(description=None)
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[row]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post("/api/v1/companies", json={"name": "Solo Corp"})
        assert response.status_code == 200

    def test_create_rejects_missing_name(self, client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            response = client.post("/api/v1/companies", json={"description": "No name"})
        assert response.status_code == 422

    def test_create_rejects_description_over_1000(self, client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            response = client.post(
                "/api/v1/companies", json={"name": "Test", "description": "x" * 1001}
            )
        assert response.status_code == 422

    def test_create_db_failure_raises_500(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post("/api/v1/companies", json={"name": "Fail Corp"})
        # ValidationError → 400
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Task 2: List companies
# ---------------------------------------------------------------------------


class TestListCompanies:
    def test_list_returns_companies(self, client):
        rows = [_company_row(), _company_row(company_id=str(uuid4()), name="Beta Corp")]
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .eq.return_value
            .order.return_value
            .execute.return_value
        ) = MagicMock(data=rows)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get("/api/v1/companies")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_returns_empty_when_none(self, client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .eq.return_value
            .order.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get("/api/v1/companies")
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Task 3: Get single company
# ---------------------------------------------------------------------------


class TestGetCompany:
    def test_get_returns_company(self, client):
        row = _company_row()
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .single.return_value
            .execute.return_value
        ) = MagicMock(data=row)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/companies/{TEST_COMPANY_ID}")
        assert response.status_code == 200
        assert response.json()["name"] == "Acme Corp"

    def test_get_404_when_not_found(self, client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .single.return_value
            .execute.return_value
        ) = MagicMock(data=None)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/companies/{TEST_COMPANY_ID}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Task 4: Update company
# ---------------------------------------------------------------------------


class TestUpdateCompany:
    def test_patch_updates_name(self, client):
        updated = _company_row(name="Updated Corp")
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .update.return_value
            .eq.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[updated])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/companies/{TEST_COMPANY_ID}", json={"name": "Updated Corp"}
            )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Corp"

    def test_patch_404_when_not_found(self, client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .update.return_value
            .eq.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/companies/{TEST_COMPANY_ID}", json={"name": "Ghost Corp"}
            )
        assert response.status_code == 404

    def test_patch_rejects_description_over_1000(self, client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            response = client.patch(
                f"/api/v1/companies/{TEST_COMPANY_ID}",
                json={"description": "x" * 1001},
            )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Task 5: Delete company
# ---------------------------------------------------------------------------


class TestDeleteCompany:
    def test_delete_returns_204(self, client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .delete.return_value
            .eq.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[{"id": TEST_COMPANY_ID}])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/companies/{TEST_COMPANY_ID}")
        assert response.status_code == 204

    def test_delete_404_when_not_found(self, client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .delete.return_value
            .eq.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/companies/{TEST_COMPANY_ID}")
        assert response.status_code == 404
