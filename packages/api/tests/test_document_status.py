"""
Document status endpoint tests — KIN-398.

Endpoint: GET /api/v1/documents/{document_id}

Covers:
  - Returns document status for an owned document.
  - Returns 404 (not 500) when document is soft-deleted or missing.
  - Returns 403 when document belongs to another user's KB.
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
OTHER_USER_ID = str(uuid4())

PATCH_DOC_SUPABASE = "app.api.routes.documents.get_supabase"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(doc_id=DOC_ID, status="completed"):
    return {
        "id": doc_id,
        "status": status,
        "error_stage": None,
        "error_message": None,
        "retry_count": 0,
        "knowledge_base_id": KB_ID,
        "tags": [],
    }


def _mock_status_fetch(mock_client, doc=None, kb_user_id=TEST_USER_ID):
    """Wire mock for get_document_status: doc fetch (limit(1)) + KB ownership check."""
    doc = doc or _make_doc()

    def _table(name):
        m = MagicMock()
        if name == "knowledge_base_documents":
            m.select.return_value.eq.return_value.is_.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[doc]
            )
        elif name == "knowledge_bases":
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"user_id": kb_user_id}
            )
        return m

    mock_client.table.side_effect = _table


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetDocumentStatus:
    """GET /api/v1/documents/{document_id}"""

    def test_returns_status_for_owned_document(self, client):
        """Returns 200 with document status for a valid owned document."""
        with patch(PATCH_DOC_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_status_fetch(mock_client, doc=_make_doc(status="completed"))

            res = client.get(f"/api/v1/documents/{DOC_ID}")

        assert res.status_code == 200
        data = res.json()
        assert data["document_id"] == DOC_ID
        assert data["status"] == "completed"
        assert data["retry_count"] == 0
        assert data["tags"] == []
        assert data["is_retryable"] is True

    def test_returns_404_when_document_deleted(self, client):
        """Returns 404 (not 500) when document is soft-deleted or missing (KIN-398).

        Root cause: .single() raises PGRST116 on 0 rows. Fix: .limit(1) returns []
        which is falsy — existing `if not result.data` guard returns 404 cleanly.
        """
        with patch(PATCH_DOC_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            # Simulate document not found — limit(1) returns empty list
            mock_client.table.return_value.select.return_value.eq.return_value.is_.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )

            res = client.get(f"/api/v1/documents/{uuid4()}")

        assert res.status_code == 404

    def test_returns_403_when_document_belongs_to_other_user(self, client):
        """Returns 403 when the document's KB belongs to another user."""
        with patch(PATCH_DOC_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_status_fetch(mock_client, kb_user_id=OTHER_USER_ID)

            res = client.get(f"/api/v1/documents/{DOC_ID}")

        assert res.status_code == 403

    def test_returns_status_with_error_fields_for_failed_doc(self, client):
        """Returns error_stage, error_message, and is_retryable=True for a retryable failure."""
        doc = {
            "id": DOC_ID,
            "status": "failed",
            "error_stage": "embedding",
            "error_message": "OpenAI API rate limit exceeded",
            "retry_count": 2,
            "knowledge_base_id": KB_ID,
            "tags": [],
        }
        with patch(PATCH_DOC_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_status_fetch(mock_client, doc=doc)

            res = client.get(f"/api/v1/documents/{DOC_ID}")

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "failed"
        assert data["error_stage"] == "embedding"
        assert data["error_message"] == "OpenAI API rate limit exceeded"
        assert data["retry_count"] == 2
        assert data["is_retryable"] is True

    def test_token_limit_failure_returns_is_retryable_false(self, client):
        """Returns is_retryable=False when error_message contains 'token limit' (KIN-408)."""
        doc = {
            "id": DOC_ID,
            "status": "failed",
            "error_stage": "extracting",
            "error_message": "Document exceeds token limit: 3,320,528 > 1,000,000",
            "retry_count": 0,
            "knowledge_base_id": KB_ID,
            "tags": [],
        }
        with patch(PATCH_DOC_SUPABASE) as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            _mock_status_fetch(mock_client, doc=doc)

            res = client.get(f"/api/v1/documents/{DOC_ID}")

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "failed"
        assert data["is_retryable"] is False
