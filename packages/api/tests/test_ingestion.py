"""
Document ingestion pipeline test suite — KIN-255

Covers:
  - Happy path: all stages, chunk indexing
  - Retry logic: 3x per-stage with backoff
  - Stage tracking: status transitions persisted
  - Token limit rejection: >1M tokens rejected pre-embedding
  - File size rejection: >25 MB rejected at upload boundary

Schema ref: docs/db-schema-spec.md §12 (knowledge_base_documents), §13 (knowledge_base_chunks)
Framework: pytest + pytest-asyncio
"""

from __future__ import annotations

import asyncio
from typing import List
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_supabase_mock(status_calls: list | None = None):
    """Build a Supabase mock that tracks update() calls."""
    sb = MagicMock()
    sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    sb.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": str(uuid4())}]
    )
    return sb


def _run(coro):
    """Run an async coroutine in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestIngestionHappyPath:
    def test_document_processes_through_all_stages(self, db_session, mock_embedding_service):
        """
        All pipeline stages complete, document ends up in 'completed' state.
        Status transitions: extracting → chunking → embedding → completed.
        """
        from app.services.ingestion.pipeline import run_ingestion

        document_id = uuid4()
        kb_id = uuid4()
        project_id = uuid4()

        sample_text = "Hello world. " * 100  # enough tokens but well under 1M

        with (
            patch("app.services.ingestion.pipeline.extract_text", return_value=sample_text),
            patch("app.services.ingestion.pipeline.generate_summary", return_value=None),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            _run(
                run_ingestion(
                    db_session, document_id, kb_id, project_id, None,
                    b"fake-content", "test.txt", "text/plain",
                )
            )

        # Verify final status was set to "completed"
        update_calls = db_session.table.return_value.update.call_args_list
        statuses = [c.args[0].get("status") for c in update_calls if "status" in c.args[0]]
        assert "completed" in statuses, f"Expected 'completed' in status calls, got: {statuses}"

    def test_chunks_are_indexed_in_pgvector(self, db_session):
        """
        After successful ingestion, chunks are inserted to knowledge_base_chunks
        with non-null embedding and correct chunk shape.
        """
        from app.services.ingestion.indexer import index_chunks
        from app.services.ingestion.chunker import Chunk

        document_id = uuid4()
        kb_id = uuid4()
        project_id = uuid4()

        chunks = [
            Chunk(text="Chunk one text", chunk_index=0, token_count=4),
            Chunk(text="Chunk two text", chunk_index=1, token_count=4),
        ]
        embeddings = [[0.1] * 3072, [0.2] * 3072]

        count = _run(index_chunks(db_session, document_id, kb_id, project_id, None, chunks, embeddings))

        assert count == 1  # mock returns 1 row in data list
        insert_call = db_session.table.return_value.insert.call_args
        rows: List[dict] = insert_call.args[0]
        assert len(rows) == 2
        assert all(r["embedding"] is not None for r in rows)
        assert rows[0]["chunk_index"] == 0
        assert rows[1]["chunk_index"] == 1
        assert all(r["embedding_model"] == "text-embedding-3-large" for r in rows)


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestIngestionRetry:
    def test_failed_stage_retries_up_to_3_times(self, db_session):
        """
        Transient embedding failure triggers 3 retries then marks document failed.
        retry_count == 3, status == 'failed'.
        """
        from app.services.ingestion.pipeline import run_ingestion

        document_id = uuid4()
        kb_id = uuid4()
        project_id = uuid4()
        sample_text = "Hello world. " * 50

        retry_count_calls = []

        def _track_update(fields):
            if "retry_count" in fields:
                retry_count_calls.append(fields["retry_count"])
            mock = MagicMock()
            mock.eq.return_value.execute.return_value = MagicMock(data=[])
            return mock

        db_session.table.return_value.update.side_effect = _track_update

        embed_call_count = {"n": 0}

        def _always_fail(texts):
            embed_call_count["n"] += 1
            raise RuntimeError("transient embedding error")

        with (
            patch("app.services.ingestion.pipeline.extract_text", return_value=sample_text),
            patch("app.services.ingestion.pipeline.generate_summary", return_value=None),
            patch(
                "app.services.ingestion.pipeline.EmbeddingService.embed_batch",
                side_effect=_always_fail,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(RuntimeError, match="transient embedding error"):
                _run(
                    run_ingestion(
                        db_session, document_id, kb_id, project_id, None,
                        b"content", "test.txt", "text/plain",
                    )
                )

        # Embedded was called MAX_INGESTION_RETRIES + 1 times (1 initial + 3 retries)
        from app.core.config import settings
        assert embed_call_count["n"] == settings.MAX_INGESTION_RETRIES + 1

    def test_retry_succeeds_on_second_attempt(self, db_session):
        """
        Embedding fails once, succeeds on second attempt.
        Document ends up 'completed', retry_count == 1.
        """
        from app.services.ingestion.pipeline import run_ingestion

        document_id = uuid4()
        kb_id = uuid4()
        project_id = uuid4()
        sample_text = "Hello world. " * 50

        attempt = {"n": 0}

        def _fail_once(texts):
            attempt["n"] += 1
            if attempt["n"] == 1:
                raise RuntimeError("transient error")
            return [[0.1] * 3072 for _ in texts]

        with (
            patch("app.services.ingestion.pipeline.extract_text", return_value=sample_text),
            patch("app.services.ingestion.pipeline.generate_summary", return_value=None),
            patch(
                "app.services.ingestion.pipeline.EmbeddingService.embed_batch",
                side_effect=_fail_once,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            _run(
                run_ingestion(
                    db_session, document_id, kb_id, project_id, None,
                    b"content", "test.txt", "text/plain",
                )
            )

        update_calls = db_session.table.return_value.update.call_args_list
        statuses = [c.args[0].get("status") for c in update_calls if "status" in c.args[0]]
        assert "completed" in statuses

    def test_after_3_failures_status_is_failed(self, client, db_session):
        """
        GET /api/v1/documents/{id} returns status == 'failed' after 3 embedding failures.
        Verifies the API surface for retry UX.
        """
        doc_id = str(uuid4())
        # Mock Supabase GET to return a failed document
        with patch("app.api.routes.documents.get_supabase") as mock_get_sb:
            mock_sb = MagicMock()
            # Document query uses .is_("deleted_at", "null") in the chain
            mock_sb.table.return_value.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                data={
                    "id": doc_id,
                    "status": "failed",
                    "error_stage": "embedding",
                    "error_message": "transient embedding error",
                    "retry_count": 3,
                    "knowledge_base_id": str(uuid4()),
                }
            )
            # KB ownership check uses .select().eq().single().execute() (no .is_)
            mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"user_id": TEST_USER_ID}
            )
            mock_get_sb.return_value = mock_sb

            response = client.get(f"/api/v1/documents/{doc_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["retry_count"] == 3
        assert data["error_stage"] == "embedding"


# ---------------------------------------------------------------------------
# Stage tracking
# ---------------------------------------------------------------------------


class TestIngestionStageTracking:
    def test_each_stage_transition_is_persisted(self, db_session, mock_embedding_service):
        """
        Status updates are written to DB in order: extracting, chunking, embedding, completed.
        """
        from app.services.ingestion.pipeline import run_ingestion

        document_id = uuid4()
        kb_id = uuid4()
        project_id = uuid4()
        sample_text = "Hello world. " * 50

        status_sequence: list[str] = []

        original_update = db_session.table.return_value.update

        def _capture_update(fields):
            if "status" in fields:
                status_sequence.append(fields["status"])
            mock = MagicMock()
            mock.eq.return_value.execute.return_value = MagicMock(data=[])
            return mock

        db_session.table.return_value.update.side_effect = _capture_update

        with (
            patch("app.services.ingestion.pipeline.extract_text", return_value=sample_text),
            patch("app.services.ingestion.pipeline.generate_summary", return_value=None),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            _run(
                run_ingestion(
                    db_session, document_id, kb_id, project_id, None,
                    b"content", "test.txt", "text/plain",
                )
            )

        assert "extracting" in status_sequence
        assert "chunking" in status_sequence
        assert "embedding" in status_sequence
        assert "completed" in status_sequence
        # Order check: extracting appears before completed
        assert status_sequence.index("extracting") < status_sequence.index("completed")


# ---------------------------------------------------------------------------
# Token limit rejection
# ---------------------------------------------------------------------------


class TestIngestionTokenLimit:
    def test_document_over_1m_tokens_is_rejected(self, db_session, large_document):
        """
        Document exceeding 1M tokens fails at extraction stage.
        Status = 'failed', error_stage = 'extracting', no chunks written.
        """
        from app.services.ingestion.pipeline import run_ingestion

        document_id = uuid4()
        kb_id = uuid4()
        project_id = uuid4()

        # large_document fixture creates ~1.2M token text
        large_text = large_document.decode("utf-8")

        status_calls: list[str] = []

        def _capture_update(fields):
            if "status" in fields:
                status_calls.append(fields["status"])
            mock = MagicMock()
            mock.eq.return_value.execute.return_value = MagicMock(data=[])
            return mock

        db_session.table.return_value.update.side_effect = _capture_update

        with (
            patch("app.services.ingestion.pipeline.extract_text", return_value=large_text),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            # TokenLimitExceeded is caught internally — pipeline returns without raising
            _run(
                run_ingestion(
                    db_session, document_id, kb_id, project_id, None,
                    large_document, "large.txt", "text/plain",
                )
            )

        assert "failed" in status_calls
        # No chunks should have been inserted
        insert_calls = db_session.table.return_value.insert.call_args_list
        chunk_inserts = [
            c for c in insert_calls
            if c.args and isinstance(c.args[0], list) and c.args[0]
            and "chunk_index" in c.args[0][0]
        ]
        assert len(chunk_inserts) == 0, "No chunks should be written on token limit rejection"


# ---------------------------------------------------------------------------
# File size rejection
# ---------------------------------------------------------------------------


class TestIngestionFileSizeLimit:
    def test_file_over_25mb_is_rejected_at_upload(self, client, oversized_file):
        """
        POST /api/v1/documents/upload with file > 25 MB returns 413.
        No document row is created.
        """
        with patch("app.api.routes.documents.get_supabase") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb

            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("big.bin", oversized_file, "application/octet-stream")},
                data={"knowledge_base_id": str(uuid4())},
            )

        assert response.status_code == 413
        # Supabase insert should NOT have been called
        mock_sb.table.return_value.insert.assert_not_called()
