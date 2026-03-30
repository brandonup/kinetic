"""
Tests for KIN-380: Conversation CRUD endpoints.

Covers:
  - Create conversation (TestCreateConversation)
  - List conversations (TestListConversations)
  - Get single conversation (TestGetConversation)
  - Update conversation (TestUpdateConversation)
  - Delete conversation (TestDeleteConversation)

All Supabase calls are mocked. Uses client fixture from conftest.py.
Schema ref: docs/db-schema-spec.md §5 (conversations)
"""

from unittest.mock import MagicMock, patch, call
from uuid import uuid4

import pytest

TEST_CONV_ID = str(uuid4())
TEST_COMPANY_ID = str(uuid4())
TEST_PROJECT_ID = str(uuid4())
PATCH_TARGET = "app.api.routes.conversations.get_supabase_client"


def _conv_row(
    conv_id: str = TEST_CONV_ID,
    company_id: str = TEST_COMPANY_ID,
    project_id: str | None = TEST_PROJECT_ID,
    title: str | None = "Fix auth bug",
    active_agent_id: str | None = None,
) -> dict:
    return {
        "id": conv_id,
        "user_id": str(uuid4()),
        "company_id": company_id,
        "project_id": project_id,
        "title": title,
        "active_agent_id": active_agent_id,
        "deleted_at": None,
        "created_at": "2026-03-26T10:00:00+00:00",
        "updated_at": "2026-03-26T10:00:00+00:00",
    }


def _make_mock_db():
    """Create a fresh MagicMock for Supabase client with fluent API chaining."""
    return MagicMock()


def _wire_company_owned(mock_db: MagicMock) -> None:
    """Wire the company ownership check to succeed."""
    chain = mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value
    chain.maybe_single.return_value.execute.return_value = MagicMock(data={"id": TEST_COMPANY_ID})


def _wire_company_not_owned(mock_db: MagicMock) -> None:
    """Wire the company ownership check to fail."""
    chain = mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value
    chain.maybe_single.return_value.execute.return_value = MagicMock(data=None)


# ---------------------------------------------------------------------------
# Create conversation
# ---------------------------------------------------------------------------


class TestCreateConversation:
    def test_create_returns_201(self, client):
        row = _conv_row()
        mock_db = _make_mock_db()
        _wire_company_owned(mock_db)
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[row]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/conversations",
                json={"company_id": TEST_COMPANY_ID, "title": "Fix auth bug"},
            )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Fix auth bug"
        assert data["company_id"] == TEST_COMPANY_ID

    def test_create_with_project_id(self, client):
        row = _conv_row(project_id=TEST_PROJECT_ID)
        mock_db = _make_mock_db()
        _wire_company_owned(mock_db)
        # Project lookup returns matching company
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": TEST_PROJECT_ID, "company_id": TEST_COMPANY_ID}
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[row]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/conversations",
                json={
                    "company_id": TEST_COMPANY_ID,
                    "project_id": TEST_PROJECT_ID,
                    "title": "Fix auth bug",
                },
            )
        assert response.status_code == 201

    def test_create_rejects_unowned_company(self, client):
        mock_db = _make_mock_db()
        _wire_company_not_owned(mock_db)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/conversations",
                json={"company_id": TEST_COMPANY_ID},
            )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# List conversations
# ---------------------------------------------------------------------------


class TestListConversations:
    def test_list_returns_conversations(self, client):
        rows = [_conv_row(), _conv_row(conv_id=str(uuid4()), title="Second conv")]
        mock_db = _make_mock_db()
        _wire_company_owned(mock_db)
        # Wire the query chain for list
        mock_db.table.return_value.select.return_value.eq.return_value.is_.return_value.order.return_value.limit.return_value.eq.return_value.execute.return_value = MagicMock(
            data=rows
        )
        # Wire project_name enrichment
        mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": TEST_PROJECT_ID, "name": "Kinetic"}]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(
                f"/api/v1/conversations?company_id={TEST_COMPANY_ID}"
            )
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data

    def test_list_empty(self, client):
        mock_db = _make_mock_db()
        # Wire the list query to return empty — need to handle the fluent chain
        mock_db.table.return_value.select.return_value.eq.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get("/api/v1/conversations")
        assert response.status_code == 200
        data = response.json()
        assert data["conversations"] == []

    def test_list_rejects_unowned_company(self, client):
        mock_db = _make_mock_db()
        _wire_company_not_owned(mock_db)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(
                f"/api/v1/conversations?company_id={TEST_COMPANY_ID}"
            )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Get conversation
# ---------------------------------------------------------------------------


class TestGetConversation:
    def test_get_returns_conversation(self, client):
        row = _conv_row()
        mock_db = _make_mock_db()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
            data=row
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/conversations/{TEST_CONV_ID}")
        assert response.status_code == 200
        assert response.json()["id"] == TEST_CONV_ID

    def test_get_not_found(self, client):
        mock_db = _make_mock_db()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(f"/api/v1/conversations/{str(uuid4())}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update conversation
# ---------------------------------------------------------------------------


class TestUpdateConversation:
    def test_update_title(self, client):
        row = _conv_row(title="Updated title")
        mock_db = _make_mock_db()
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[row]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/conversations/{TEST_CONV_ID}",
                json={"title": "Updated title"},
            )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated title"

    def test_update_not_found(self, client):
        mock_db = _make_mock_db()
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/conversations/{str(uuid4())}",
                json={"title": "New title"},
            )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Delete conversation (soft-delete)
# ---------------------------------------------------------------------------


class TestDeleteConversation:
    def test_delete_returns_204(self, client):
        mock_db = _make_mock_db()
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[_conv_row()]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/conversations/{TEST_CONV_ID}")
        assert response.status_code == 204

    def test_delete_not_found(self, client):
        mock_db = _make_mock_db()
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/conversations/{str(uuid4())}")
        assert response.status_code == 404
