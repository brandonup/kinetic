"""
Background job hardening tests — KIN-338

Covers:
  - Stale job cleanup: docs stuck in processing states marked failed
  - Retry dedup: concurrent retries get 409 (atomic check-and-update)

Schema ref: docs/db-schema-spec.md §12 (knowledge_base_documents)
Framework: pytest + pytest-asyncio
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID


def _run(coro):
    """Run an async coroutine in tests (matches test_ingestion.py pattern)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Stale job cleanup
# ---------------------------------------------------------------------------


class TestStaleJobCleanup:
    def test_stale_pending_docs_are_marked_failed(self):
        """Documents stuck in 'pending' for >30 min are marked failed."""
        from app.services.background import cleanup_stale_jobs

        mock_sb = MagicMock()
        # Null error_message path (first update per status): returns 2 docs
        mock_sb.table.return_value.update.return_value.eq.return_value.lt.return_value.is_.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[{"id": str(uuid4())}, {"id": str(uuid4())}]
        )
        # Non-null error_message path (second update per status): returns 0
        mock_sb.table.return_value.update.return_value.eq.return_value.lt.return_value.is_.return_value.not_.is_.return_value.execute.return_value = MagicMock(
            data=[]
        )

        result = _run(cleanup_stale_jobs(mock_sb))

        assert result >= 2
        update_calls = mock_sb.table.return_value.update.call_args_list
        assert any(c.args[0].get("status") == "failed" for c in update_calls)

    def test_no_stale_docs_returns_zero(self):
        """When no docs are stale, returns 0."""
        from app.services.background import cleanup_stale_jobs

        mock_sb = MagicMock()
        mock_sb.table.return_value.update.return_value.eq.return_value.lt.return_value.is_.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_sb.table.return_value.update.return_value.eq.return_value.lt.return_value.is_.return_value.not_.is_.return_value.execute.return_value = MagicMock(
            data=[]
        )

        result = _run(cleanup_stale_jobs(mock_sb))
        assert result == 0

    def test_cleanup_continues_on_individual_status_failure(self):
        """If cleanup fails for one status, other statuses still get cleaned."""
        from app.services.background import cleanup_stale_jobs

        mock_sb = MagicMock()
        call_count = {"n": 0}

        def _alternate_response(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call (first status, null error_message path) fails
                raise RuntimeError("DB error")
            mock_result = MagicMock()
            mock_result.data = [{"id": str(uuid4())}]
            return mock_result

        # Both update chains share the same execute side_effect via MagicMock chaining
        mock_sb.table.return_value.update.return_value.eq.return_value.lt.return_value.is_.return_value.is_.return_value.execute.side_effect = _alternate_response
        mock_sb.table.return_value.update.return_value.eq.return_value.lt.return_value.is_.return_value.not_.is_.return_value.execute.side_effect = _alternate_response

        result = _run(cleanup_stale_jobs(mock_sb))
        assert result >= 1

    def test_stale_error_message_includes_state_name(self):
        """Stale job error message includes the stuck status name."""
        from app.services.background import cleanup_stale_jobs

        mock_sb = MagicMock()
        captured_updates = []

        def _capture_update(fields):
            captured_updates.append(fields)
            mock_chain = MagicMock()
            return mock_chain

        mock_sb.table.return_value.update.side_effect = _capture_update

        _run(cleanup_stale_jobs(mock_sb))

        # First update per status includes error_message with the state name
        error_messages = [u.get("error_message", "") for u in captured_updates if u.get("error_message")]
        assert any("pending" in msg for msg in error_messages)

    def test_stale_cleanup_preserves_existing_error_message(self):
        """Docs with existing error_message keep it — only status+error_stage are updated."""
        from app.services.background import cleanup_stale_jobs

        mock_sb = MagicMock()
        captured_updates = []

        def _capture_update(fields):
            captured_updates.append(fields)
            return MagicMock()

        mock_sb.table.return_value.update.side_effect = _capture_update

        _run(cleanup_stale_jobs(mock_sb))

        # Second update per status (preserve path) must NOT include error_message
        preserve_updates = [u for u in captured_updates if "error_message" not in u]
        assert len(preserve_updates) > 0
        for u in preserve_updates:
            assert u.get("status") == "failed"
            assert "error_stage" in u


# ---------------------------------------------------------------------------
# Retry dedup (atomic check-and-update)
# ---------------------------------------------------------------------------


class TestRetryDedup:
    def test_concurrent_retry_gets_409(self, client):
        """If another retry already claimed the doc, returns 409."""
        doc_id = str(uuid4())
        kb_id = str(uuid4())

        with (
            patch("app.api.routes.documents.get_supabase") as mock_get_sb,
            patch("app.api.routes.documents.run_ingestion_from_stage", new_callable=AsyncMock),
        ):
            mock_sb = MagicMock()

            # Document fetch: status=failed
            mock_sb.table.return_value.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                data={
                    "id": doc_id,
                    "status": "failed",
                    "error_stage": "embedding",
                    "storage_uri": f"{doc_id}/test.txt",
                    "knowledge_base_id": kb_id,
                    "file_type": "text/plain",
                    "title": "test.txt",
                }
            )

            # KB ownership check
            mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={
                    "user_id": TEST_USER_ID,
                    "project_id": str(uuid4()),
                    "agent_definition_id": None,
                }
            )

            # Storage download
            mock_sb.storage.from_.return_value.download.return_value = b"text content"

            # Chunk cleanup
            mock_sb.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

            # Atomic update returns EMPTY data — another retry already changed status
            mock_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )

            mock_get_sb.return_value = mock_sb

            response = client.post(f"/api/v1/documents/{doc_id}/retry")

        assert response.status_code == 409
        assert "already in progress" in response.json()["detail"]
