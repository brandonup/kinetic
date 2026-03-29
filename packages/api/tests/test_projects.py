"""
Tests for KIN-263: Project CRUD + KIN-370: Project Knowledge Base

Covers:
  - Create project (TestCreateProject)
  - List projects (TestListProjects)
  - Get single project (TestGetProject)
  - Update project (TestUpdateProject)
  - Delete project (TestDeleteProject)
  - Project Knowledge Base GET/POST (TestProjectKnowledgeBase)

All Supabase calls are mocked. Uses client fixture from conftest.py.
Schema ref: docs/db-schema-spec.md §4 (projects), §10 (knowledge_bases)
Spec ref: docs/specs/kin-257-projects-conversations-spec.md §Part 1
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

TEST_PROJECT_ID = str(uuid4())
TEST_COMPANY_ID = str(uuid4())
PATCH_TARGET = "app.api.routes.projects.get_supabase_client"


def _project_row(
    project_id: str = TEST_PROJECT_ID,
    company_id: str = TEST_COMPANY_ID,
    name: str = "Test Project",
    instructions: str = "Be concise.",
) -> dict:
    return {
        "id": project_id,
        "company_id": company_id,
        "user_id": str(uuid4()),
        "name": name,
        "instructions": instructions,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _mock_company_owned(mock_db):
    """Wire the company ownership check to succeed (returns a company row)."""
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": TEST_COMPANY_ID}
    )


def _mock_company_not_owned(mock_db):
    """Wire the company ownership check to fail (returns None)."""
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data=None
    )


# ---------------------------------------------------------------------------
# Create project
# ---------------------------------------------------------------------------


class TestCreateProject:
    def test_create_returns_201(self, client):
        row = _project_row()
        mock_db = MagicMock()
        _mock_company_owned(mock_db)
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[row]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/projects",
                json={"name": "Test Project", "company_id": TEST_COMPANY_ID, "instructions": "Be concise."},
            )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["company_id"] == TEST_COMPANY_ID

    def test_create_name_only_returns_201(self, client):
        row = _project_row(instructions=None)
        mock_db = MagicMock()
        _mock_company_owned(mock_db)
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[row]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/projects",
                json={"name": "Minimal Project", "company_id": TEST_COMPANY_ID},
            )
        assert response.status_code == 201

    def test_create_missing_name_returns_422(self, client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            response = client.post(
                "/api/v1/projects", json={"company_id": TEST_COMPANY_ID}
            )
        assert response.status_code == 422

    def test_create_empty_name_returns_422(self, client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            response = client.post(
                "/api/v1/projects", json={"name": "", "company_id": TEST_COMPANY_ID}
            )
        assert response.status_code == 422

    def test_create_company_not_owned_returns_403(self, client):
        mock_db = MagicMock()
        _mock_company_not_owned(mock_db)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/projects",
                json={"name": "Bad Co Project", "company_id": str(uuid4())},
            )
        assert response.status_code == 403

    def test_create_db_failure_returns_400(self, client):
        mock_db = MagicMock()
        _mock_company_owned(mock_db)
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/projects",
                json={"name": "Ghost", "company_id": TEST_COMPANY_ID},
            )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# List projects
# ---------------------------------------------------------------------------


class TestListProjects:
    def test_list_returns_projects_shape(self, client):
        rows = [_project_row(), _project_row(project_id=str(uuid4()), name="Second")]
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .eq.return_value
            .order.return_value
            .execute.return_value
        ) = MagicMock(data=rows)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get("/api/v1/projects")
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert len(data["projects"]) == 2

    def test_list_empty_returns_projects_shape(self, client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .eq.return_value
            .order.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get("/api/v1/projects")
        assert response.status_code == 200
        assert response.json() == {"projects": []}

    def test_list_with_company_filter(self, client):
        row = _project_row()
        mock_db = MagicMock()
        _mock_company_owned(mock_db)
        (
            mock_db.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .order.return_value
            .execute.return_value
        ) = MagicMock(data=[row])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/projects?company_id={TEST_COMPANY_ID}")
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data

    def test_list_company_filter_not_owned_returns_403(self, client):
        mock_db = MagicMock()
        _mock_company_not_owned(mock_db)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/projects?company_id={str(uuid4())}")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Get single project
# ---------------------------------------------------------------------------


class TestGetProject:
    def test_get_returns_project(self, client):
        row = _project_row()
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
            response = client.get(f"/api/v1/projects/{TEST_PROJECT_ID}")
        assert response.status_code == 200
        assert response.json()["name"] == "Test Project"

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
            response = client.get(f"/api/v1/projects/{TEST_PROJECT_ID}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update project
# ---------------------------------------------------------------------------


class TestUpdateProject:
    def test_patch_name(self, client):
        updated = _project_row(name="Renamed")
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
                f"/api/v1/projects/{TEST_PROJECT_ID}", json={"name": "Renamed"}
            )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"

    def test_patch_with_company_change(self, client):
        new_company_id = str(uuid4())
        updated = _project_row(company_id=new_company_id)
        mock_db = MagicMock()
        _mock_company_owned(mock_db)
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[updated]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/projects/{TEST_PROJECT_ID}",
                json={"company_id": new_company_id},
            )
        assert response.status_code == 200

    def test_patch_company_not_owned_returns_403(self, client):
        mock_db = MagicMock()
        _mock_company_not_owned(mock_db)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/projects/{TEST_PROJECT_ID}",
                json={"company_id": str(uuid4())},
            )
        assert response.status_code == 403

    def test_patch_not_found_returns_404(self, client):
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
                f"/api/v1/projects/{TEST_PROJECT_ID}", json={"name": "Ghost"}
            )
        assert response.status_code == 404

    def test_patch_empty_name_returns_422(self, client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            response = client.patch(
                f"/api/v1/projects/{TEST_PROJECT_ID}", json={"name": ""}
            )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Delete project
# ---------------------------------------------------------------------------


class TestDeleteProject:
    def test_delete_returns_204(self, client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .delete.return_value
            .eq.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[{"id": TEST_PROJECT_ID}])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/projects/{TEST_PROJECT_ID}")
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
            response = client.delete(f"/api/v1/projects/{TEST_PROJECT_ID}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Project Knowledge Base — KIN-370
# ---------------------------------------------------------------------------

TEST_KB_ID = str(uuid4())


def _make_kb_mock_db(project_data, kb_data, insert_data=None):
    """
    Build a mock Supabase client that routes table("projects") and table("knowledge_bases")
    to separate mock chains. Each chain supports .select().eq().eq().single().execute()
    and .select().eq().execute() patterns.
    """
    mock_db = MagicMock()

    project_mock = MagicMock()
    project_mock.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data=project_data
    )

    kb_mock = MagicMock()
    kb_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=kb_data
    )
    if insert_data is not None:
        kb_mock.insert.return_value.execute.return_value = MagicMock(data=insert_data)

    def table_router(table_name):
        if table_name == "projects":
            return project_mock
        if table_name == "knowledge_bases":
            return kb_mock
        return MagicMock()

    mock_db.table.side_effect = table_router
    return mock_db


class TestProjectKnowledgeBase:
    """GET /api/v1/projects/{id}/knowledge-base and POST .../knowledge-base"""

    # -- GET: KB found --
    def test_get_kb_returns_200(self, client):
        mock_db = _make_kb_mock_db(
            project_data={"id": TEST_PROJECT_ID},
            kb_data=[{"id": TEST_KB_ID}],
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/projects/{TEST_PROJECT_ID}/knowledge-base")
        assert response.status_code == 200
        assert response.json() == {"id": TEST_KB_ID}

    # -- GET: project not found / not owned --
    def test_get_kb_project_not_found_returns_404(self, client):
        mock_db = _make_kb_mock_db(
            project_data=None,
            kb_data=[],
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/projects/{TEST_PROJECT_ID}/knowledge-base")
        assert response.status_code == 404

    # -- GET: project exists but no KB --
    def test_get_kb_no_kb_returns_404(self, client):
        mock_db = _make_kb_mock_db(
            project_data={"id": TEST_PROJECT_ID},
            kb_data=[],
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/projects/{TEST_PROJECT_ID}/knowledge-base")
        assert response.status_code == 404

    # -- POST: create new KB --
    def test_create_kb_returns_201(self, client):
        mock_db = _make_kb_mock_db(
            project_data={"id": TEST_PROJECT_ID},
            kb_data=[],
            insert_data=[{"id": TEST_KB_ID}],
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(f"/api/v1/projects/{TEST_PROJECT_ID}/knowledge-base")
        assert response.status_code == 201
        assert response.json() == {"id": TEST_KB_ID}

    # -- POST: idempotent (existing KB) returns 200 --
    def test_create_kb_idempotent_returns_200(self, client):
        mock_db = _make_kb_mock_db(
            project_data={"id": TEST_PROJECT_ID},
            kb_data=[{"id": TEST_KB_ID}],
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(f"/api/v1/projects/{TEST_PROJECT_ID}/knowledge-base")
        assert response.status_code == 200
        assert response.json() == {"id": TEST_KB_ID}

    # -- POST: project not found --
    def test_create_kb_project_not_found_returns_404(self, client):
        mock_db = _make_kb_mock_db(
            project_data=None,
            kb_data=[],
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(f"/api/v1/projects/{TEST_PROJECT_ID}/knowledge-base")
        assert response.status_code == 404

    # -- POST: insert failure --
    def test_create_kb_insert_failure_returns_400(self, client):
        mock_db = _make_kb_mock_db(
            project_data={"id": TEST_PROJECT_ID},
            kb_data=[],
            insert_data=[],
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(f"/api/v1/projects/{TEST_PROJECT_ID}/knowledge-base")
        assert response.status_code == 400
