"""
KB management routes tests — KIN-345.

Endpoints: folder CRUD, document list, tag update.
All tests mock Supabase client — no real DB calls.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KB_ID = str(uuid4())
FOLDER_ID = str(uuid4())
DOC_ID = str(uuid4())
USER_ID = TEST_USER_ID

PATCH_SUPABASE = "app.api.routes.kb_management.get_supabase"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kb_owned_mock(mock_client):
    """Wire KB ownership check to pass."""
    def _table(name):
        m = MagicMock()
        if name == "knowledge_bases":
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"id": KB_ID, "user_id": USER_ID}
            )
        return m
    mock_client.table.side_effect = _table


def _kb_owned_with_folders(mock_client, folders=None):
    """Wire KB ownership + folder list."""
    folders = folders or []
    call_count = {"n": 0}

    def _table(name):
        m = MagicMock()
        if name == "knowledge_bases":
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"id": KB_ID, "user_id": USER_ID}
            )
        elif name == "knowledge_base_folders":
            call_count["n"] += 1
            # List call
            m.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=folders
            )
            # Insert call (create)
            m.insert.return_value.execute.return_value = MagicMock(data=folders[:1] if folders else [])
            # Update call (rename)
            m.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=folders[:1] if folders else []
            )
            # Single check (delete verification)
            m.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=folders[0] if folders else None
            )
            # Delete
            m.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        elif name == "knowledge_base_documents":
            m.select.return_value.eq.return_value.is_.return_value.order.return_value.execute.return_value = MagicMock(
                data=[]
            )
            # Reassign update
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return m

    mock_client.table.side_effect = _table


# ---------------------------------------------------------------------------
# Document list
# ---------------------------------------------------------------------------


class TestListDocuments:
    def test_list_documents_returns_empty(self, client):
        mock_client = MagicMock()

        def _table(name):
            m = MagicMock()
            if name == "knowledge_bases":
                m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": KB_ID, "user_id": USER_ID}
                )
            elif name == "knowledge_base_documents":
                m.select.return_value.eq.return_value.is_.return_value.order.return_value.execute.return_value = MagicMock(
                    data=[]
                )
            return m

        mock_client.table.side_effect = _table

        with patch(PATCH_SUPABASE, return_value=mock_client):
            resp = client.get(f"/api/v1/knowledge-bases/{KB_ID}/documents")

        assert resp.status_code == 200
        assert resp.json()["documents"] == []

    def test_list_documents_wrong_user_404(self, client):
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": KB_ID, "user_id": "other-user"}
        )

        with patch(PATCH_SUPABASE, return_value=mock_client):
            resp = client.get(f"/api/v1/knowledge-bases/{KB_ID}/documents")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


class TestFolderCRUD:
    def test_list_folders(self, client):
        mock_client = MagicMock()
        folders = [{"id": FOLDER_ID, "knowledge_base_id": KB_ID, "name": "Research", "created_at": "2026-03-24T00:00:00Z"}]
        _kb_owned_with_folders(mock_client, folders)

        with patch(PATCH_SUPABASE, return_value=mock_client):
            resp = client.get(f"/api/v1/knowledge-bases/{KB_ID}/folders")

        assert resp.status_code == 200
        assert len(resp.json()["folders"]) == 1
        assert resp.json()["folders"][0]["name"] == "Research"

    def test_create_folder(self, client):
        mock_client = MagicMock()
        new_folder = {"id": FOLDER_ID, "knowledge_base_id": KB_ID, "name": "Notes", "created_at": "2026-03-24T00:00:00Z"}

        def _table(name):
            m = MagicMock()
            if name == "knowledge_bases":
                m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": KB_ID, "user_id": USER_ID}
                )
            elif name == "knowledge_base_folders":
                m.insert.return_value.execute.return_value = MagicMock(data=[new_folder])
            return m

        mock_client.table.side_effect = _table

        with patch(PATCH_SUPABASE, return_value=mock_client):
            resp = client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/folders",
                json={"name": "Notes"},
            )

        assert resp.status_code == 201
        assert resp.json()["name"] == "Notes"

    def test_create_folder_empty_name_rejected(self, client):
        mock_client = MagicMock()
        _kb_owned_mock(mock_client)

        with patch(PATCH_SUPABASE, return_value=mock_client):
            resp = client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/folders",
                json={"name": "  "},
            )

        assert resp.status_code == 422

    def test_rename_folder(self, client):
        mock_client = MagicMock()
        renamed = {"id": FOLDER_ID, "knowledge_base_id": KB_ID, "name": "Renamed", "created_at": "2026-03-24T00:00:00Z"}

        def _table(name):
            m = MagicMock()
            if name == "knowledge_bases":
                m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": KB_ID, "user_id": USER_ID}
                )
            elif name == "knowledge_base_folders":
                m.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[renamed]
                )
            return m

        mock_client.table.side_effect = _table

        with patch(PATCH_SUPABASE, return_value=mock_client):
            resp = client.patch(
                f"/api/v1/knowledge-bases/{KB_ID}/folders/{FOLDER_ID}",
                json={"name": "Renamed"},
            )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    def test_delete_folder_reassigns_documents(self, client):
        mock_client = MagicMock()
        folder = {"id": FOLDER_ID, "knowledge_base_id": KB_ID, "name": "Old", "created_at": "2026-03-24T00:00:00Z"}
        _kb_owned_with_folders(mock_client, [folder])

        with patch(PATCH_SUPABASE, return_value=mock_client):
            resp = client.delete(
                f"/api/v1/knowledge-bases/{KB_ID}/folders/{FOLDER_ID}",
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert resp.json()["reassigned_to"] is None

    def test_delete_folder_reassign_to_valid_target(self, client):
        """Delete folder with reassign_to pointing to another folder in the same KB."""
        target_folder_id = str(uuid4())
        mock_client = MagicMock()
        folder = {"id": FOLDER_ID, "knowledge_base_id": KB_ID, "name": "Old", "created_at": "2026-03-24T00:00:00Z"}
        target = {"id": target_folder_id, "knowledge_base_id": KB_ID, "name": "Target", "created_at": "2026-03-24T00:00:00Z"}

        call_count = {"n": 0}

        def _table(name):
            m = MagicMock()
            call_count["n"] += 1
            if name == "knowledge_bases":
                m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": KB_ID, "user_id": USER_ID}
                )
            elif name == "knowledge_base_folders":
                # First call: folder exists check. Second call: target validation.
                m.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data=folder if call_count["n"] <= 3 else target
                )
                m.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif name == "knowledge_base_documents":
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_client.table.side_effect = _table

        with patch(PATCH_SUPABASE, return_value=mock_client):
            resp = client.delete(
                f"/api/v1/knowledge-bases/{KB_ID}/folders/{FOLDER_ID}?reassign_to={target_folder_id}",
            )

        assert resp.status_code == 200
        assert resp.json()["reassigned_to"] == target_folder_id

    def test_delete_folder_reassign_to_cross_kb_rejected(self, client):
        """Delete folder with reassign_to pointing to folder in a different KB → 400."""
        foreign_folder_id = str(uuid4())
        mock_client = MagicMock()
        folder = {"id": FOLDER_ID, "knowledge_base_id": KB_ID, "name": "Old", "created_at": "2026-03-24T00:00:00Z"}

        folder_call = {"n": 0}

        def _table(name):
            m = MagicMock()
            if name == "knowledge_bases":
                m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": KB_ID, "user_id": USER_ID}
                )
            elif name == "knowledge_base_folders":
                folder_call["n"] += 1
                if folder_call["n"] == 1:
                    # First folder call: folder exists check — passes
                    m.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                        data=folder
                    )
                else:
                    # Second folder call: target validation — fails (not in this KB)
                    m.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                        data=None
                    )
            return m

        mock_client.table.side_effect = _table

        with patch(PATCH_SUPABASE, return_value=mock_client):
            resp = client.delete(
                f"/api/v1/knowledge-bases/{KB_ID}/folders/{FOLDER_ID}?reassign_to={foreign_folder_id}",
            )

        assert resp.status_code == 400
        assert "target folder" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class TestTagUpdate:
    def test_update_tags(self, client):
        mock_client = MagicMock()

        call_count = {"n": 0}

        def _table(name):
            m = MagicMock()
            call_count["n"] += 1
            if name == "knowledge_base_documents":
                if call_count["n"] == 1:
                    # Ownership check — doc lookup
                    m.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                        data={"id": DOC_ID, "knowledge_base_id": KB_ID, "tags": []}
                    )
                else:
                    # Tag update
                    m.update.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"id": DOC_ID, "tags": ["strategy", "ai"]}]
                    )
            elif name == "knowledge_bases":
                m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"user_id": USER_ID}
                )
            return m

        mock_client.table.side_effect = _table

        with patch(PATCH_SUPABASE, return_value=mock_client):
            resp = client.patch(
                f"/api/v1/documents/{DOC_ID}/tags",
                json={"tags": ["strategy", "ai"]},
            )

        assert resp.status_code == 200
        assert resp.json()["tags"] == ["strategy", "ai"]

    def test_update_tags_wrong_user_404(self, client):
        mock_client = MagicMock()

        call_count = {"n": 0}

        def _table(name):
            m = MagicMock()
            call_count["n"] += 1
            if name == "knowledge_base_documents":
                m.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": DOC_ID, "knowledge_base_id": KB_ID, "tags": []}
                )
            elif name == "knowledge_bases":
                m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"user_id": "other-user"}
                )
            return m

        mock_client.table.side_effect = _table

        with patch(PATCH_SUPABASE, return_value=mock_client):
            resp = client.patch(
                f"/api/v1/documents/{DOC_ID}/tags",
                json={"tags": ["test"]},
            )

        assert resp.status_code == 404
