"""
Tests for KIN-326: Admin RAG Debug tab.

Covers:
  - TraceWriter (TestTraceWriter) — sync write function, silent failure
  - List traces (TestRagDebugList) — admin-only, scope filter, cursor pagination
  - Trace detail (TestRagDebugDetail) — full trace + enriched chunk join, 404, admin-only

All Supabase calls are mocked. Uses client + admin_client fixtures from conftest.py.
Schema ref: docs/db-schema-spec.md §20 (retrieval_debug_logs)
Spec ref:   docs/specs/rag-debug-tab-spec.md
"""

from unittest.mock import MagicMock, patch
from urllib.parse import quote
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRACE_PATCH = "app.api.routes.admin_rag_debug.get_supabase_client"

TRACE_ID = str(uuid4())
MSG_ID = str(uuid4())
CHUNK_ID_1 = str(uuid4())
CHUNK_ID_2 = str(uuid4())
DOC_ID_1 = str(uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trace_summary(
    trace_id: str = TRACE_ID,
    scope: str = "project_kb",
    gating_decision: str = "injected",
    injected_count: int = 3,
    vector_count: int = 20,
) -> dict:
    """A summary row as returned by the list endpoint."""
    return {
        "id": trace_id,
        "message_id": MSG_ID,
        "scope": scope,
        "query_text": "How do I set up authentication?",
        "gating_decision": gating_decision,
        "injected_chunks": [{"chunk_id": CHUNK_ID_1, "score": 0.85, "text_preview": "Auth setup..."} for _ in range(injected_count)],
        "vector_candidates": [{"chunk_id": str(uuid4()), "score": 0.5} for _ in range(vector_count)],
        "created_at": "2026-03-23T12:00:00+00:00",
    }


def _trace_full() -> dict:
    """A full trace row as returned by the detail endpoint (pre-enrichment)."""
    return {
        "id": TRACE_ID,
        "message_id": MSG_ID,
        "scope": "project_kb",
        "query_text": "How do I set up authentication?",
        "query_variants": None,
        "vector_candidates": [{"chunk_id": CHUNK_ID_1, "score": 0.9}, {"chunk_id": CHUNK_ID_2, "score": 0.7}],
        "mmr_selections": [{"chunk_id": CHUNK_ID_1, "score": 0.9}],
        "rerank_scores": None,
        "gating_decision": "injected",
        "injected_chunks": [{"chunk_id": CHUNK_ID_1, "score": 0.9, "text_preview": "Auth setup docs..."}],
        "error_message": None,
        "created_at": "2026-03-23T12:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Task 2: Trace Writer
# ---------------------------------------------------------------------------


class TestTraceWriter:
    def test_write_retrieval_trace_inserts_row(self):
        """write_retrieval_trace() inserts a row into retrieval_debug_logs."""
        from app.services.rag.trace_writer import write_retrieval_trace

        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": TRACE_ID}])

        write_retrieval_trace(
            message_id=MSG_ID,
            scope="project_kb",
            query_text="test query",
            vector_candidates=[{"chunk_id": CHUNK_ID_1, "score": 0.9}],
            mmr_selections=[{"chunk_id": CHUNK_ID_1, "score": 0.9}],
            injected_chunks=[{"chunk_id": CHUNK_ID_1, "score": 0.9, "text_preview": "..."}],
            gating_decision="injected",
            supabase=mock_db,
        )

        mock_db.table.assert_called_once_with("retrieval_debug_logs")
        inserted_row = mock_db.table.return_value.insert.call_args[0][0]
        assert inserted_row["message_id"] == MSG_ID
        assert inserted_row["scope"] == "project_kb"
        assert inserted_row["query_text"] == "test query"
        assert inserted_row["gating_decision"] == "injected"
        assert inserted_row["error_message"] is None

    def test_write_retrieval_trace_includes_error_message(self):
        """write_retrieval_trace() persists error_message when embedding fails."""
        from app.services.rag.trace_writer import write_retrieval_trace

        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": TRACE_ID}])

        write_retrieval_trace(
            message_id=MSG_ID,
            scope="project_kb",
            query_text="test query",
            vector_candidates=[],
            mmr_selections=[],
            injected_chunks=[],
            gating_decision="error",
            supabase=mock_db,
            error_message="OpenAI embedding API timeout",
        )

        inserted_row = mock_db.table.return_value.insert.call_args[0][0]
        assert inserted_row["gating_decision"] == "error"
        assert inserted_row["error_message"] == "OpenAI embedding API timeout"

    def test_write_retrieval_trace_db_failure_is_silent(self):
        """write_retrieval_trace() swallows DB errors — never propagates to caller."""
        from app.services.rag.trace_writer import write_retrieval_trace

        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.side_effect = RuntimeError("DB unavailable")

        # Should not raise
        write_retrieval_trace(
            message_id=MSG_ID,
            scope="project_kb",
            query_text="test query",
            vector_candidates=[],
            mmr_selections=[],
            injected_chunks=[],
            gating_decision="below_threshold",
            supabase=mock_db,
        )


# ---------------------------------------------------------------------------
# Task 3: Admin RAG Debug List Endpoint
# ---------------------------------------------------------------------------


class TestRagDebugList:
    def test_list_returns_traces_with_summary_fields(self, admin_client):
        """GET /api/v1/admin/rag-debug returns trace list with computed count fields."""
        row = _trace_summary()
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[row]
        )

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get("/api/v1/admin/rag-debug")

        assert resp.status_code == 200
        body = resp.json()
        assert "traces" in body
        assert len(body["traces"]) == 1
        trace = body["traces"][0]
        assert trace["id"] == TRACE_ID
        assert trace["scope"] == "project_kb"
        assert trace["gating_decision"] == "injected"
        # computed count fields
        assert trace["injected_chunk_count"] == 3
        assert trace["vector_candidate_count"] == 20

    def test_list_scope_filter_applied(self, admin_client):
        """GET /api/v1/admin/rag-debug?scope=agent_kb applies eq filter on scope column."""
        mock_db = MagicMock()
        # With scope filter, the chain includes .eq("scope", ...) before .limit()
        mock_db.table.return_value.select.return_value.order.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get("/api/v1/admin/rag-debug?scope=agent_kb")

        assert resp.status_code == 200
        mock_db.table.return_value.select.return_value.order.return_value.eq.assert_called_once_with(
            "scope", "agent_kb"
        )

    def test_list_cursor_pagination_filters_by_created_at(self, admin_client):
        """GET /api/v1/admin/rag-debug?cursor=<iso> applies lt filter on created_at."""
        cursor_ts = "2026-03-23T12:00:00+00:00"
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.order.return_value.lt.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        # URL-encode the cursor so '+' is preserved (not decoded to space) by ASGI
        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/rag-debug?cursor={quote(cursor_ts, safe='')}")

        assert resp.status_code == 200
        mock_db.table.return_value.select.return_value.order.return_value.lt.assert_called_once_with(
            "created_at", cursor_ts
        )

    def test_list_next_cursor_set_when_full_page_returned(self, admin_client):
        """next_cursor is the created_at of the last item when a full page is returned."""
        rows = [_trace_summary(trace_id=str(uuid4())) for _ in range(2)]
        rows[-1]["created_at"] = "2026-03-23T10:00:00+00:00"
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=rows
        )

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get("/api/v1/admin/rag-debug?limit=2")

        assert resp.status_code == 200
        assert resp.json()["next_cursor"] == "2026-03-23T10:00:00+00:00"

    def test_list_next_cursor_null_when_partial_page(self, admin_client):
        """next_cursor is null when fewer rows than limit are returned."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[_trace_summary()]  # 1 row with limit=50 → partial page
        )

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get("/api/v1/admin/rag-debug")

        assert resp.json()["next_cursor"] is None

    def test_list_non_admin_returns_403(self, client):
        """Non-admin users cannot access the RAG debug list endpoint."""
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app

        async def _raise_auth_error():
            raise AuthorizationError()

        app.dependency_overrides[require_admin] = _raise_auth_error
        try:
            resp = client.get("/api/v1/admin/rag-debug")
        finally:
            del app.dependency_overrides[require_admin]
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Task 4: Admin RAG Debug Detail Endpoint
# ---------------------------------------------------------------------------


class TestRagDebugDetail:
    def test_detail_returns_full_trace(self, admin_client):
        """GET /api/v1/admin/rag-debug/{id} returns full trace row."""
        full_trace = _trace_full()
        chunk_meta = [
            {
                "id": CHUNK_ID_1,
                "section_path": "§3.2",
                "document_id": DOC_ID_1,
                "knowledge_base_documents": {"title": "Auth Guide"},
            }
        ]

        mock_db = MagicMock()
        # First execute: fetch trace row
        # Second execute: fetch chunk metadata
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=full_trace
        )
        mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=chunk_meta
        )

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/rag-debug/{TRACE_ID}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == TRACE_ID
        assert body["query_text"] == "How do I set up authentication?"
        assert body["gating_decision"] == "injected"
        # Injected chunks must be enriched with document metadata
        injected = body["injected_chunks"]
        assert len(injected) == 1
        assert injected[0]["document_title"] == "Auth Guide"
        assert injected[0]["section_path"] == "§3.2"

    def test_detail_not_found_returns_404(self, admin_client):
        """GET /api/v1/admin/rag-debug/{id} returns 404 when trace does not exist."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/rag-debug/{uuid4()}")

        assert resp.status_code == 404

    def test_detail_no_chunks_skips_join(self, admin_client):
        """When injected_chunks is empty, the chunk metadata join is not performed."""
        trace_no_chunks = _trace_full()
        trace_no_chunks["injected_chunks"] = []

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=trace_no_chunks
        )

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/rag-debug/{TRACE_ID}")

        assert resp.status_code == 200
        # No chunk lookup: table("knowledge_base_chunks") should NOT have been called
        called_tables = [call.args[0] for call in mock_db.table.call_args_list]
        assert "knowledge_base_chunks" not in called_tables

    def test_detail_non_admin_returns_403(self, client):
        """Non-admin users cannot access the RAG debug detail endpoint."""
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app

        async def _raise_auth_error():
            raise AuthorizationError()

        app.dependency_overrides[require_admin] = _raise_auth_error
        try:
            resp = client.get(f"/api/v1/admin/rag-debug/{TRACE_ID}")
        finally:
            del app.dependency_overrides[require_admin]
        assert resp.status_code == 403
