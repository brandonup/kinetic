"""
Tests for Admin Request Trace endpoints.

Covers:
  - List traces (TestRequestTraceList) — admin-only, scope filter, timing in response
  - Trace detail (TestRequestTraceDetail) — timings + pipeline_stages, chunk enrichment, 404
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

TRACE_PATCH = "app.api.routes.admin_request_trace.get_supabase_client"

TRACE_ID = str(uuid4())
MSG_ID = str(uuid4())
CHUNK_ID_1 = str(uuid4())
DOC_ID_1 = str(uuid4())


def _trace_summary(
    trace_id: str = TRACE_ID,
    scope: str = "project_kb",
    gating_decision: str = "injected",
    retrieval_duration_ms: int = 245,
) -> dict:
    """A summary row as returned by the list query."""
    return {
        "id": trace_id,
        "message_id": MSG_ID,
        "scope": scope,
        "query_text": "How do I set up authentication?",
        "gating_decision": gating_decision,
        "retrieval_duration_ms": retrieval_duration_ms,
        "injected_chunks": [{"chunk_id": CHUNK_ID_1, "score": 0.85, "text_preview": "Auth setup..."}],
        "vector_candidates": [{"chunk_id": str(uuid4()), "score": 0.5} for _ in range(20)],
        "created_at": "2026-03-26T12:00:00+00:00",
    }


def _trace_full(
    timings: dict | None = None,
    retrieval_duration_ms: int = 245,
) -> dict:
    """A full trace row as returned by the detail query."""
    return {
        "id": TRACE_ID,
        "message_id": MSG_ID,
        "scope": "project_kb",
        "query_text": "How do I set up authentication?",
        "query_variants": None,
        "vector_candidates": [{"chunk_id": CHUNK_ID_1, "score": 0.9}],
        "mmr_selections": [{"chunk_id": CHUNK_ID_1, "score": 0.9}],
        "rerank_scores": None,
        "gating_decision": "injected",
        "injected_chunks": [{"chunk_id": CHUNK_ID_1, "score": 0.9, "text_preview": "Auth setup..."}],
        "error_message": None,
        "retrieval_duration_ms": retrieval_duration_ms,
        "timings": timings or {
            "embed": [0, 45],
            "vector_search": [45, 180],
            "mmr": [180, 195],
            "threshold": [195, 196],
            "budget": [196, 200],
            "citation": [200, 205],
        },
        "created_at": "2026-03-26T12:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# List Traces
# ---------------------------------------------------------------------------


class TestRequestTraceList:
    def test_list_returns_traces_with_timing(self, admin_client):
        """GET /api/v1/admin/request-trace returns traces including retrieval_duration_ms."""
        row = _trace_summary()
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[row])

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get("/api/v1/admin/request-trace")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["traces"]) == 1
        trace = data["traces"][0]
        assert trace["retrieval_duration_ms"] == 245
        assert trace["injected_chunk_count"] == 1
        assert trace["vector_candidate_count"] == 20

    def test_list_scope_filter(self, admin_client):
        """GET /api/v1/admin/request-trace?scope=agent_kb applies filter."""
        mock_db = MagicMock()
        mock_result = MagicMock(data=[])
        query_chain = mock_db.table.return_value.select.return_value.order.return_value
        query_chain.eq.return_value.limit.return_value.execute.return_value = mock_result

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get("/api/v1/admin/request-trace?scope=agent_kb")

        assert resp.status_code == 200
        # Verify .eq() was called with scope filter
        query_chain.eq.assert_called_once_with("scope", "agent_kb")

    def test_list_requires_admin(self, client):
        """GET /api/v1/admin/request-trace returns 403 for non-admin."""
        resp = client.get("/api/v1/admin/request-trace")
        assert resp.status_code == 403

    def test_list_cursor_pagination(self, admin_client):
        """Cursor pagination returns next_cursor when full page returned."""
        rows = [_trace_summary(trace_id=str(uuid4())) for _ in range(25)]
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=rows)

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get("/api/v1/admin/request-trace?limit=25")

        data = resp.json()
        assert data["next_cursor"] is not None


# ---------------------------------------------------------------------------
# Trace Detail
# ---------------------------------------------------------------------------


class TestRequestTraceDetail:
    def test_detail_returns_timing_and_pipeline_stages(self, admin_client):
        """GET /api/v1/admin/request-trace/{id} returns timings + computed pipeline_stages."""
        full = _trace_full()
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=full)
        # Chunk enrichment query — return empty
        mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/request-trace/{TRACE_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["retrieval_duration_ms"] == 245
        assert data["timings"]["embed"] == [0, 45]
        assert len(data["pipeline_stages"]) == 6
        # Verify stages are sorted by start_ms
        starts = [s["start_ms"] for s in data["pipeline_stages"]]
        assert starts == sorted(starts)
        # Verify first stage
        assert data["pipeline_stages"][0]["name"] == "embed"
        assert data["pipeline_stages"][0]["duration_ms"] == 45

    def test_detail_enriches_injected_chunks(self, admin_client):
        """Detail endpoint joins chunk metadata from knowledge_base_chunks."""
        full = _trace_full()
        mock_db = MagicMock()

        # First call: trace row
        trace_exec = MagicMock(data=full)
        # Second call: chunk metadata
        chunk_meta = MagicMock(data=[{
            "id": CHUNK_ID_1,
            "section_path": "section/auth",
            "document_id": DOC_ID_1,
            "knowledge_base_documents": {"title": "Auth Guide"},
        }])

        call_count = {"n": 0}
        original_table = mock_db.table

        def table_side_effect(name):
            call_count["n"] += 1
            result = MagicMock()
            if name == "retrieval_debug_logs":
                result.select.return_value.eq.return_value.single.return_value.execute.return_value = trace_exec
            elif name == "knowledge_base_chunks":
                result.select.return_value.in_.return_value.execute.return_value = chunk_meta
            return result

        mock_db.table = MagicMock(side_effect=table_side_effect)

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/request-trace/{TRACE_ID}")

        assert resp.status_code == 200
        chunks = resp.json()["injected_chunks"]
        assert len(chunks) == 1
        assert chunks[0]["document_title"] == "Auth Guide"
        assert chunks[0]["section_path"] == "section/auth"

    def test_detail_404_for_missing_trace(self, admin_client):
        """GET /api/v1/admin/request-trace/{id} returns 404 for nonexistent trace."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=None)

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/request-trace/{str(uuid4())}")

        assert resp.status_code == 404

    def test_detail_requires_admin(self, client):
        """GET /api/v1/admin/request-trace/{id} returns 403 for non-admin."""
        resp = client.get(f"/api/v1/admin/request-trace/{TRACE_ID}")
        assert resp.status_code == 403

    def test_detail_handles_null_timings(self, admin_client):
        """Detail endpoint handles traces with no timing data (pre-instrumentation rows)."""
        full = _trace_full(timings=None, retrieval_duration_ms=None)
        full["retrieval_duration_ms"] = None
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=full)

        with patch(TRACE_PATCH, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/request-trace/{TRACE_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["pipeline_stages"] == []
        assert data["retrieval_duration_ms"] is None
