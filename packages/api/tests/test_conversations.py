"""
Tests for conversation CRUD endpoints — KIN-272.

Spec ref: docs/specs/kin-257-projects-conversations-spec.md §2.2
Schema ref: docs/db-schema-spec.md §5
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_USER_ID = str(uuid4())
TEST_COMPANY_ID = str(uuid4())
TEST_PROJECT_ID = str(uuid4())
TEST_CONV_ID = str(uuid4())
TEST_AGENT_ID = str(uuid4())

PATCH_DB = "app.api.routes.conversations.get_supabase_client"

_CONV_ROW = {
    "id": TEST_CONV_ID,
    "user_id": TEST_USER_ID,
    "company_id": TEST_COMPANY_ID,
    "project_id": None,
    "title": None,
    "active_agent_id": None,
    "created_at": "2026-03-23T00:00:00Z",
    "updated_at": "2026-03-23T00:00:00Z",
}

_MSG_ROW = {
    "id": str(uuid4()),
    "role": "user",
    "content": "Hello",
    "agent_definition_id": None,
    "model": None,
    "sequence": 0,
    "created_at": "2026-03-23T00:00:00Z",
}


# ---------------------------------------------------------------------------
# Supabase mock builder
# ---------------------------------------------------------------------------


def _mock_chain(return_data: list | dict | None):
    """Return a mock supabase query chain whose .execute() returns result.data."""
    result = MagicMock()
    result.data = return_data
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.delete.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.is_.return_value = chain
    chain.order.return_value = chain
    chain.maybe_single.return_value = chain
    chain.execute.return_value = result
    return chain, result


# ---------------------------------------------------------------------------
# POST /api/v1/conversations
# ---------------------------------------------------------------------------


class TestCreateConversation:
    def test_create_company_level_conversation(self, client):
        mock_sb = MagicMock()

        # company ownership check → found
        company_chain, company_result = _mock_chain(_CONV_ROW)
        company_result.data = {"id": TEST_COMPANY_ID}

        # insert → returns row
        insert_chain, insert_result = _mock_chain([_CONV_ROW])

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            if name == "companies":
                return company_chain
            if name == "conversations":
                return insert_chain
            return MagicMock()

        mock_sb.table.side_effect = table_side_effect

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.post(
                "/api/v1/conversations",
                json={"company_id": TEST_COMPANY_ID},
            )

        assert res.status_code == 201
        assert res.json()["company_id"] == TEST_COMPANY_ID

    def test_create_project_conversation(self, client):
        mock_sb = MagicMock()

        company_chain, company_result = _mock_chain({"id": TEST_COMPANY_ID})
        project_chain, project_result = _mock_chain({"id": TEST_PROJECT_ID})
        project_company_chain, project_company_result = _mock_chain(
            {"id": TEST_PROJECT_ID}
        )
        conv_row = {**_CONV_ROW, "project_id": TEST_PROJECT_ID}
        insert_chain, insert_result = _mock_chain([conv_row])

        tables_called = []

        def table_side_effect(name):
            tables_called.append(name)
            if name == "companies":
                return company_chain
            if name == "projects":
                # first call: ownership check, second: company check
                if tables_called.count("projects") == 1:
                    return project_chain
                return project_company_chain
            if name == "conversations":
                return insert_chain
            return MagicMock()

        mock_sb.table.side_effect = table_side_effect

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.post(
                "/api/v1/conversations",
                json={
                    "company_id": TEST_COMPANY_ID,
                    "project_id": TEST_PROJECT_ID,
                },
            )

        assert res.status_code == 201
        assert res.json()["project_id"] == TEST_PROJECT_ID

    def test_create_rejects_unknown_company(self, client):
        mock_sb = MagicMock()
        company_chain, company_result = _mock_chain(None)

        mock_sb.table.return_value = company_chain

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.post(
                "/api/v1/conversations",
                json={"company_id": str(uuid4())},
            )

        assert res.status_code == 403

    def test_create_rejects_missing_company_id(self, client):
        res = client.post("/api/v1/conversations", json={})
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/conversations
# ---------------------------------------------------------------------------


class TestListConversations:
    def test_list_returns_conversations(self, client):
        mock_sb = MagicMock()
        chain, result = _mock_chain([_CONV_ROW])
        mock_sb.table.return_value = chain

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.get("/api/v1/conversations")

        assert res.status_code == 200
        assert isinstance(res.json()["conversations"], list)

    def test_list_returns_empty_when_none(self, client):
        mock_sb = MagicMock()
        chain, result = _mock_chain([])
        mock_sb.table.return_value = chain

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.get("/api/v1/conversations")

        assert res.status_code == 200
        assert res.json()["conversations"] == []

    def test_list_with_company_filter_verifies_ownership(self, client):
        mock_sb = MagicMock()
        company_chain, company_result = _mock_chain(None)  # not found

        mock_sb.table.return_value = company_chain

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.get(
                f"/api/v1/conversations?company_id={str(uuid4())}"
            )

        assert res.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/conversations/{id}
# ---------------------------------------------------------------------------


class TestGetConversation:
    def test_get_returns_conversation_with_messages(self, client):
        mock_sb = MagicMock()
        conv_chain, conv_result = _mock_chain(_CONV_ROW)
        msg_chain, msg_result = _mock_chain([_MSG_ROW])

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            if name == "conversations":
                return conv_chain
            if name == "messages":
                return msg_chain
            return MagicMock()

        mock_sb.table.side_effect = table_side_effect

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.get(f"/api/v1/conversations/{TEST_CONV_ID}")

        assert res.status_code == 200
        data = res.json()
        assert data["id"] == TEST_CONV_ID
        assert isinstance(data["messages"], list)
        assert data["messages"][0]["role"] == "user"

    def test_get_returns_404_when_not_found(self, client):
        mock_sb = MagicMock()
        conv_chain, conv_result = _mock_chain(None)
        mock_sb.table.return_value = conv_chain

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.get(f"/api/v1/conversations/{str(uuid4())}")

        assert res.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/conversations/{id}
# ---------------------------------------------------------------------------


class TestUpdateConversation:
    def test_rename_conversation(self, client):
        mock_sb = MagicMock()
        existing_chain, existing_result = _mock_chain({"id": TEST_CONV_ID})
        updated_row = {**_CONV_ROW, "title": "My new title"}
        update_chain, update_result = _mock_chain([updated_row])

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            if name == "conversations":
                if call_count[0] == 1:
                    return existing_chain
                return update_chain
            return MagicMock()

        mock_sb.table.side_effect = table_side_effect

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.patch(
                f"/api/v1/conversations/{TEST_CONV_ID}",
                json={"title": "My new title"},
            )

        assert res.status_code == 200
        assert res.json()["title"] == "My new title"

    def test_update_returns_404_when_not_found(self, client):
        mock_sb = MagicMock()
        chain, result = _mock_chain(None)
        mock_sb.table.return_value = chain

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.patch(
                f"/api/v1/conversations/{str(uuid4())}",
                json={"title": "X"},
            )

        assert res.status_code == 404

    def test_set_agent_checks_visibility(self, client):
        """Setting an inaccessible private agent returns 403."""
        mock_sb = MagicMock()
        existing_chain, _ = _mock_chain({"id": TEST_CONV_ID})
        private_agent = {
            "id": TEST_AGENT_ID,
            "visibility": "private",
            "owner_id": str(uuid4()),  # different user
        }
        agent_chain, _ = _mock_chain(private_agent)

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            if name == "conversations":
                return existing_chain
            if name == "agent_definitions":
                return agent_chain
            return MagicMock()

        mock_sb.table.side_effect = table_side_effect

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.patch(
                f"/api/v1/conversations/{TEST_CONV_ID}",
                json={"active_agent_id": TEST_AGENT_ID},
            )

        assert res.status_code == 403

    def test_deactivate_agent_sets_null(self, client):
        mock_sb = MagicMock()
        existing_chain, _ = _mock_chain({"id": TEST_CONV_ID})
        updated_row = {**_CONV_ROW, "active_agent_id": None}
        update_chain, _ = _mock_chain([updated_row])

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            if name == "conversations":
                if call_count[0] == 1:
                    return existing_chain
                return update_chain
            return MagicMock()

        mock_sb.table.side_effect = table_side_effect

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.patch(
                f"/api/v1/conversations/{TEST_CONV_ID}",
                json={"active_agent_id": None},
            )

        assert res.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /api/v1/conversations/{id}
# ---------------------------------------------------------------------------


class TestDeleteConversation:
    def test_soft_delete_returns_204(self, client):
        mock_sb = MagicMock()
        existing_chain, _ = _mock_chain({"id": TEST_CONV_ID})
        delete_chain, _ = _mock_chain([{"id": TEST_CONV_ID}])

        call_count = [0]

        def table_side_effect(name):
            call_count[0] += 1
            if name == "conversations":
                if call_count[0] == 1:
                    return existing_chain
                return delete_chain
            return MagicMock()

        mock_sb.table.side_effect = table_side_effect

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.delete(f"/api/v1/conversations/{TEST_CONV_ID}")

        assert res.status_code == 204

    def test_delete_returns_404_when_not_found(self, client):
        mock_sb = MagicMock()
        chain, result = _mock_chain(None)
        mock_sb.table.return_value = chain

        with patch(PATCH_DB, return_value=mock_sb):
            res = client.delete(f"/api/v1/conversations/{str(uuid4())}")

        assert res.status_code == 404
