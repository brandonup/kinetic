"""
Document delete endpoint tests — KIN-378, updated KIN-405.

Endpoints:
  DELETE /api/v1/documents/{document_id}          — hard-delete single document
  DELETE /api/v1/knowledge-bases/{kb_id}/documents — hard-delete all documents

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
DOC_ID = str(uuid4())
DOC_ID_2 = str(uuid4())
OTHER_USER_ID = str(uuid4())
USER_ID = TEST_USER_ID

PATCH_DOC_SUPABASE = "app.api.routes.documents.get_supabase"
PATCH_KB_SUPABASE = "app.api.routes.kb_management.get_supabase"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(doc_id=DOC_ID, status="completed", storage_uri=None):
    return {
        "id": doc_id,
        "status": status,
        "knowledge_base_id": KB_ID,
        "title": "test.pdf",
        "storage_uri": storage_uri or f"{doc_id}/test.pdf",
        "tags": [],
    }


def _mock_single_delete(mock_client, doc=None, kb_user_id=USER_ID):
    """Wire mock for single document hard-delete flow."""
    doc = doc or _make_doc()
    call_count = {"n": 0}

    def _table(name):
        nonlocal call_count
        m = MagicMock()
        if name == "knowledge_base_documents":
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call: fetch document (select with limit(1), no deleted_at filter)
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[doc]
                )
            else:
                # Subsequent call: hard-delete
                m.delete.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[doc]
                )
        elif name == "knowledge_bases":
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"user_id": kb_user_id}
            )
        return m

    mock_client.table.side_effect = _table
    mock_client.storage.from_.return_value.remove.return_value = None


def _mock_delete_all(mock_client, docs=None, kb_user_id=USER_ID):
    """Wire mock for delete-all hard-delete flow."""
    docs = docs if docs is not None else [_make_doc()]
    call_count = {"n": 0}

    def _table(name):
        nonlocal call_count
        m = MagicMock()
        if name == "knowledge_bases":
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"id": KB_ID, "user_id": kb_user_id}
            )
        elif name == "knowledge_base_documents":
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call: fetch all documents (select)
                m.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
                    data=docs
                )
            else:
                # Second call: hard-delete (scoped to non-deleted rows)
                m.delete.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
                    data=docs
                )
        return m

    mock_client.table.side_effect = _table
    mock_client.storage.from_.return_value.remove.return_value = None


# ---------------------------------------------------------------------------
# Single delete tests
# ---------------------------------------------------------------------------


class TestDeleteDocument:
    """DELETE /api/v1/documents/{document_id} — hard-delete"""

    def test_successful_delete(self, client):
        """Hard-delete returns 200, document_id, and deleted=true."""
        with patch(PATCH_DOC_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_single_delete(mock_client)

            res = client.delete(f"/api/v1/documents/{DOC_ID}")

        assert res.status_code == 200
        data = res.json()
        assert data["document_id"] == DOC_ID
        assert data["deleted"] is True

    def test_active_ingestion_returns_409(self, client):
        """Delete on actively-ingesting document returns 409."""
        for status in ("extracting", "chunking", "embedding"):
            with patch(PATCH_DOC_SUPABASE) as mock_get:
                mock_client = MagicMock()
                mock_get.return_value = mock_client
                _mock_single_delete(mock_client, doc=_make_doc(status=status))

                res = client.delete(f"/api/v1/documents/{DOC_ID}")

            assert res.status_code == 409, f"Expected 409 for status={status}"

    def test_not_found_returns_404(self, client):
        """Delete on non-existent document returns 404."""
        with patch(PATCH_DOC_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )

            res = client.delete(f"/api/v1/documents/{uuid4()}")

        assert res.status_code == 404

    def test_other_users_document_returns_404(self, client):
        """Cannot delete another user's document (404 for anti-enumeration)."""
        with patch(PATCH_DOC_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_single_delete(mock_client, kb_user_id=OTHER_USER_ID)

            res = client.delete(f"/api/v1/documents/{DOC_ID}")

        assert res.status_code == 404

    def test_storage_failure_does_not_fail_request(self, client):
        """Storage cleanup failure is non-fatal — delete still returns 200."""
        with patch(PATCH_DOC_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_single_delete(mock_client)
            mock_client.storage.from_.return_value.remove.side_effect = Exception("Storage unavailable")

            res = client.delete(f"/api/v1/documents/{DOC_ID}")

        assert res.status_code == 200
        assert res.json()["deleted"] is True

    def test_pending_and_failed_are_deletable(self, client):
        """Documents with status pending, completed, or failed can be deleted."""
        for status in ("pending", "completed", "failed"):
            with patch(PATCH_DOC_SUPABASE) as mock_get:
                mock_client = MagicMock()
                mock_get.return_value = mock_client
                _mock_single_delete(mock_client, doc=_make_doc(status=status))

                res = client.delete(f"/api/v1/documents/{DOC_ID}")

            assert res.status_code == 200, f"Expected 200 for status={status}"


# ---------------------------------------------------------------------------
# Delete-all tests
# ---------------------------------------------------------------------------


class TestDeleteAllDocuments:
    """DELETE /api/v1/knowledge-bases/{kb_id}/documents — hard-delete all"""

    def test_successful_delete_all(self, client):
        """Delete-all returns 200 with count of hard-deleted documents."""
        docs = [_make_doc(DOC_ID), _make_doc(DOC_ID_2)]
        with patch(PATCH_KB_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_delete_all(mock_client, docs=docs)

            res = client.delete(f"/api/v1/knowledge-bases/{KB_ID}/documents")

        assert res.status_code == 200
        data = res.json()
        assert data["knowledge_base_id"] == KB_ID
        assert data["deleted_count"] == 2

    def test_active_doc_returns_409(self, client):
        """Delete-all with one active doc returns 409."""
        docs = [_make_doc(DOC_ID), _make_doc(DOC_ID_2, status="extracting")]
        with patch(PATCH_KB_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_delete_all(mock_client, docs=docs)

            res = client.delete(f"/api/v1/knowledge-bases/{KB_ID}/documents")

        assert res.status_code == 409

    def test_empty_kb_returns_zero(self, client):
        """Delete-all on empty KB returns deleted_count=0."""
        with patch(PATCH_KB_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_delete_all(mock_client, docs=[])

            res = client.delete(f"/api/v1/knowledge-bases/{KB_ID}/documents")

        assert res.status_code == 200
        assert res.json()["deleted_count"] == 0

    def test_other_user_kb_returns_404(self, client):
        """Cannot delete documents in another user's KB."""
        with patch(PATCH_KB_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_delete_all(mock_client, kb_user_id=OTHER_USER_ID)

            res = client.delete(f"/api/v1/knowledge-bases/{KB_ID}/documents")

        assert res.status_code == 404

    def test_storage_failure_does_not_fail_delete_all(self, client):
        """Storage cleanup failure is non-fatal — delete-all still returns 200."""
        docs = [_make_doc(DOC_ID)]
        with patch(PATCH_KB_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_delete_all(mock_client, docs=docs)
            mock_client.storage.from_.return_value.remove.side_effect = Exception("Storage unavailable")

            res = client.delete(f"/api/v1/knowledge-bases/{KB_ID}/documents")

        assert res.status_code == 200
        assert res.json()["deleted_count"] == 1
