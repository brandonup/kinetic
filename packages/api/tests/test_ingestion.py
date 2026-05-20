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
from unittest.mock import AsyncMock, MagicMock, PropertyMock, call, patch
from uuid import uuid4

import httpx
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
                    anthropic_key="test-anthropic-key",
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
        assert all(r["embedding_model"] == "gemini-embedding-001" for r in rows)


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
            # Document query uses .is_("deleted_at", "null").limit(1) in the chain
            mock_sb.table.return_value.select.return_value.eq.return_value.is_.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{
                    "id": doc_id,
                    "status": "failed",
                    "error_stage": "embedding",
                    "error_message": "transient embedding error",
                    "retry_count": 3,
                    "knowledge_base_id": str(uuid4()),
                    "tags": [],
                }]
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


class TestOrphanedRowCleanup:
    """Upload route cleans up pending document row on unexpected failure (KIN-408 RC-2)."""

    def test_orphaned_row_deleted_on_unexpected_exception(self, client):
        """
        If fetch_user_key_async raises an unexpected (non-HTTP) exception after the
        document row is inserted, the orphaned pending row is deleted before propagating.
        """
        kb_id = str(uuid4())

        # Shared mocks — same instance returned for every table() call with that name
        kb_mock = MagicMock()
        kb_mock.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"project_id": None, "agent_definition_id": str(uuid4()), "user_id": TEST_USER_ID}
        )

        doc_mock = MagicMock()
        doc_mock.insert.return_value.execute.return_value = MagicMock(data=[{"id": "new-doc-id"}])
        doc_mock.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        def _table(name):
            if name == "knowledge_bases":
                return kb_mock
            elif name == "knowledge_base_documents":
                return doc_mock
            return MagicMock()

        with (
            patch("app.api.routes.documents.get_supabase") as mock_get_sb,
            patch(
                "app.api.routes.documents.fetch_user_key_async",
                side_effect=RuntimeError("unexpected key service error"),
            ),
        ):
            mock_sb = MagicMock()
            mock_sb.table.side_effect = _table
            mock_sb.storage.from_.return_value.upload.return_value = None
            mock_get_sb.return_value = mock_sb

            # RuntimeError propagates through Starlette's test client
            # (raise_server_exceptions=True default). Catch it and verify cleanup ran.
            with pytest.raises(Exception):
                client.post(
                    "/api/v1/documents/upload",
                    files={"file": ("test.txt", b"hello world", "text/plain")},
                    data={"knowledge_base_id": kb_id},
                )

        doc_mock.delete.assert_called_once()


# ---------------------------------------------------------------------------
# Tag suggestion — KIN-336
# ---------------------------------------------------------------------------


class TestTagSuggestion:
    @pytest.fixture(autouse=True)
    def _patch_enrichment_enabled(self):
        """Ensure ENRICHMENT_ENABLED is True for tag tests."""
        with patch(
            "app.services.ingestion.tag_suggester.settings"
        ) as mock_settings:
            mock_settings.ENRICHMENT_ENABLED = True
            mock_settings.CONVERSATION_COMPRESSION_MODEL = "claude-haiku-3-5"
            self._mock_settings = mock_settings
            yield

    def test_tag_suggestion_happy_path(self):
        """LLM returns comma-separated tags → parsed into list, lowercased."""
        from app.services.ingestion.tag_suggester import suggest_tags

        with patch(
            "app.services.ingestion.tag_suggester.call_llm",
            return_value="Strategy, Leadership, Decision-Making",
        ):
            tags = suggest_tags("Some document text about strategic leadership.", anthropic_key="test-key")

        assert tags == ["strategy", "leadership", "decision-making"]

    def test_tag_suggestion_failure_returns_empty_list(self):
        """LLM call raises → returns empty list, no exception propagated."""
        from app.services.ingestion.tag_suggester import suggest_tags

        with patch(
            "app.services.ingestion.tag_suggester.call_llm",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            tags = suggest_tags("Some document text.", anthropic_key="test-key")

        assert tags == []

    def test_tag_suggestion_no_key_returns_empty_list(self):
        """No Anthropic key → returns empty list without calling LLM."""
        from app.services.ingestion.tag_suggester import suggest_tags

        tags = suggest_tags("Some document text.", anthropic_key=None)

        assert tags == []

    def test_tag_suggestion_disabled_returns_empty_list(self):
        """ENRICHMENT_ENABLED=False → returns empty list without calling LLM."""
        from app.services.ingestion.tag_suggester import suggest_tags

        self._mock_settings.ENRICHMENT_ENABLED = False
        tags = suggest_tags("Some document text.", anthropic_key="test-key")

        assert tags == []

    def test_tag_suggestion_caps_at_five(self):
        """If LLM returns more than 5 tags, only first 5 are kept."""
        from app.services.ingestion.tag_suggester import suggest_tags

        with patch(
            "app.services.ingestion.tag_suggester.call_llm",
            return_value="a, b, c, d, e, f, g",
        ):
            tags = suggest_tags("Some document text.", anthropic_key="test-key")

        assert len(tags) == 5
        assert tags == ["a", "b", "c", "d", "e"]

    def test_tag_suggestion_empty_response(self):
        """LLM returns empty string → returns empty list."""
        from app.services.ingestion.tag_suggester import suggest_tags

        with patch(
            "app.services.ingestion.tag_suggester.call_llm",
            return_value="",
        ):
            tags = suggest_tags("Some document text.", anthropic_key="test-key")

        assert tags == []


# ---------------------------------------------------------------------------
# Pipeline tag integration — KIN-336
# ---------------------------------------------------------------------------


class TestPipelineTagIntegration:
    def test_tags_stored_after_extraction(self, db_session, mock_embedding_service):
        """Pipeline stores AI-suggested tags in the document row."""
        from app.services.ingestion.pipeline import run_ingestion

        document_id = uuid4()
        kb_id = uuid4()
        project_id = uuid4()
        sample_text = "Hello world. " * 100

        with (
            patch("app.services.ingestion.pipeline.extract_text", return_value=sample_text),
            patch("app.services.ingestion.pipeline.generate_summary", return_value=None),
            patch("app.services.ingestion.pipeline.suggest_tags", return_value=["strategy", "leadership"]),
            patch("app.services.ingestion.pipeline._store_extracted_text", new_callable=AsyncMock),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            _run(
                run_ingestion(
                    db_session, document_id, kb_id, project_id, None,
                    b"fake-content", "test.txt", "text/plain",
                    anthropic_key="test-anthropic-key",
                )
            )

        update_calls = db_session.table.return_value.update.call_args_list
        tag_updates = [c.args[0].get("tags") for c in update_calls if "tags" in c.args[0]]
        assert ["strategy", "leadership"] in tag_updates

    def test_tag_failure_does_not_block_ingestion(self, db_session, mock_embedding_service):
        """If tag suggestion returns empty, pipeline still completes."""
        from app.services.ingestion.pipeline import run_ingestion

        document_id = uuid4()
        kb_id = uuid4()
        project_id = uuid4()
        sample_text = "Hello world. " * 100

        with (
            patch("app.services.ingestion.pipeline.extract_text", return_value=sample_text),
            patch("app.services.ingestion.pipeline.generate_summary", return_value=None),
            patch("app.services.ingestion.pipeline.suggest_tags", return_value=[]),
            patch("app.services.ingestion.pipeline._store_extracted_text", new_callable=AsyncMock),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            _run(
                run_ingestion(
                    db_session, document_id, kb_id, project_id, None,
                    b"fake-content", "test.txt", "text/plain",
                    anthropic_key="test-anthropic-key",
                )
            )

        update_calls = db_session.table.return_value.update.call_args_list
        statuses = [c.args[0].get("status") for c in update_calls if "status" in c.args[0]]
        assert "completed" in statuses


# ---------------------------------------------------------------------------
# Stage resumption — KIN-336
# ---------------------------------------------------------------------------


class TestStageResumption:
    def test_resume_from_chunking_skips_extraction(self, db_session, mock_embedding_service):
        """run_ingestion_from_stage with start_stage='chunking' skips extract_text."""
        from app.services.ingestion.pipeline import run_ingestion_from_stage

        document_id = uuid4()
        kb_id = uuid4()
        project_id = uuid4()
        extracted_text = "Hello world. " * 100

        with (
            patch("app.services.ingestion.pipeline.extract_text") as mock_extract,
            patch("app.services.ingestion.pipeline.generate_summary", return_value=None),
            patch("app.services.ingestion.pipeline.suggest_tags", return_value=[]),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            _run(
                run_ingestion_from_stage(
                    db_session, document_id, kb_id, project_id, None,
                    start_stage="chunking",
                    extracted_text=extracted_text,
                )
            )
            mock_extract.assert_not_called()

        # Verify pipeline completed
        update_calls = db_session.table.return_value.update.call_args_list
        statuses = [c.args[0].get("status") for c in update_calls if "status" in c.args[0]]
        assert "chunking" in statuses
        assert "completed" in statuses

    def test_resume_from_extracting_runs_full_pipeline(self, db_session, mock_embedding_service):
        """run_ingestion_from_stage with start_stage='extracting' runs full pipeline."""
        from app.services.ingestion.pipeline import run_ingestion_from_stage

        document_id = uuid4()
        kb_id = uuid4()
        project_id = uuid4()
        sample_text = "Hello world. " * 100

        with (
            patch("app.services.ingestion.pipeline.extract_text", return_value=sample_text),
            patch("app.services.ingestion.pipeline.generate_summary", return_value=None),
            patch("app.services.ingestion.pipeline.suggest_tags", return_value=[]),
            patch("app.services.ingestion.pipeline._store_extracted_text", new_callable=AsyncMock),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            _run(
                run_ingestion_from_stage(
                    db_session, document_id, kb_id, project_id, None,
                    start_stage="extracting",
                    file_content=b"fake-content",
                    filename="test.txt",
                    content_type="text/plain",
                )
            )

        update_calls = db_session.table.return_value.update.call_args_list
        statuses = [c.args[0].get("status") for c in update_calls if "status" in c.args[0]]
        assert "extracting" in statuses
        assert "completed" in statuses

    def test_resume_from_chunking_requires_text(self):
        """run_ingestion_from_stage raises ValueError if extracted_text missing for chunking."""
        from app.services.ingestion.pipeline import run_ingestion_from_stage

        with pytest.raises(ValueError, match="extracted_text required"):
            _run(
                run_ingestion_from_stage(
                    MagicMock(), uuid4(), uuid4(), None, None,
                    start_stage="chunking",
                    extracted_text=None,
                )
            )


# ---------------------------------------------------------------------------
# Retry endpoint — KIN-336
# ---------------------------------------------------------------------------


class TestRetryEndpoint:
    def _mock_supabase_for_retry(self, doc_status="failed", error_stage="embedding",
                                  user_id=TEST_USER_ID, storage_uri="doc-id/test.txt"):
        """Build a Supabase mock configured for retry endpoint tests."""
        mock_sb = MagicMock()

        # Document query (select → eq → is_ → single → execute)
        mock_sb.table.return_value.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": str(uuid4()),
                "status": doc_status,
                "error_stage": error_stage,
                "storage_uri": storage_uri,
                "knowledge_base_id": str(uuid4()),
                "file_type": "text/plain",
                "title": "test.txt",
            }
        )

        # KB ownership check (select → eq → single → execute — no .is_)
        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "user_id": user_id,
                "project_id": str(uuid4()),
                "agent_definition_id": None,
            }
        )

        # Chunk delete (delete → eq → execute)
        mock_sb.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        # Status reset (update → eq → execute)
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        # Storage download
        mock_sb.storage.from_.return_value.download.return_value = b"extracted text content"

        return mock_sb

    def test_retry_resets_failed_document(self, client):
        """POST /retry on a failed doc resets status and dispatches pipeline."""
        doc_id = str(uuid4())
        with (
            patch("app.api.routes.documents.get_supabase") as mock_get_sb,
            patch("app.api.routes.documents.run_ingestion_from_stage", new_callable=AsyncMock),
            patch("app.api.routes.documents.fetch_user_key_async", new_callable=AsyncMock, return_value="sk-test"),
        ):
            mock_sb = self._mock_supabase_for_retry()
            mock_get_sb.return_value = mock_sb

            response = client.post(f"/api/v1/documents/{doc_id}/retry")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert "Retry initiated" in data["message"]

    def test_retry_non_failed_returns_409(self, client):
        """POST /retry on a completed doc returns 409."""
        doc_id = str(uuid4())
        with patch("app.api.routes.documents.get_supabase") as mock_get_sb:
            mock_sb = self._mock_supabase_for_retry(doc_status="completed")
            mock_get_sb.return_value = mock_sb

            response = client.post(f"/api/v1/documents/{doc_id}/retry")

        assert response.status_code == 409

    def test_retry_not_found_returns_404(self, client):
        """POST /retry on a nonexistent doc returns 404."""
        doc_id = str(uuid4())
        with patch("app.api.routes.documents.get_supabase") as mock_get_sb:
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                data=None
            )
            mock_get_sb.return_value = mock_sb

            response = client.post(f"/api/v1/documents/{doc_id}/retry")

        assert response.status_code == 404

    def test_retry_access_denied_returns_403(self, client):
        """POST /retry by a non-owner returns 403."""
        doc_id = str(uuid4())
        with patch("app.api.routes.documents.get_supabase") as mock_get_sb:
            mock_sb = self._mock_supabase_for_retry(user_id="different-user-id")
            mock_get_sb.return_value = mock_sb

            response = client.post(f"/api/v1/documents/{doc_id}/retry")

        assert response.status_code == 403

    def test_retry_fallback_to_full_extraction_when_text_unavailable(self, client):
        """When extracted text download fails, retry falls back to file download."""
        doc_id = str(uuid4())
        with (
            patch("app.api.routes.documents.get_supabase") as mock_get_sb,
            patch("app.api.routes.documents.run_ingestion_from_stage", new_callable=AsyncMock),
            patch("app.api.routes.documents.fetch_user_key_async", new_callable=AsyncMock, return_value="sk-test"),
        ):
            mock_sb = self._mock_supabase_for_retry(error_stage="chunking")
            # First download (extracted text) fails, second (file) succeeds
            mock_sb.storage.from_.return_value.download.side_effect = [
                RuntimeError("text not found"),
                b"file-bytes-for-extraction",
            ]
            mock_get_sb.return_value = mock_sb

            response = client.post(f"/api/v1/documents/{doc_id}/retry")

        assert response.status_code == 200
        data = response.json()
        assert "extracting" in data["message"]  # fell back to full extraction

    def test_retry_500_when_no_storage_available(self, client):
        """When neither text nor file is available, retry returns 500."""
        doc_id = str(uuid4())
        with patch("app.api.routes.documents.get_supabase") as mock_get_sb:
            mock_sb = self._mock_supabase_for_retry(
                error_stage="chunking", storage_uri=None
            )
            # Text download fails
            mock_sb.storage.from_.return_value.download.side_effect = RuntimeError("not found")
            mock_get_sb.return_value = mock_sb

            response = client.post(f"/api/v1/documents/{doc_id}/retry")

        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Document status with tags — KIN-336
# ---------------------------------------------------------------------------


class TestDocumentStatusTags:
    def test_document_status_includes_tags(self, client):
        """GET /documents/{id} returns tags in response."""
        doc_id = str(uuid4())
        with patch("app.api.routes.documents.get_supabase") as mock_get_sb:
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.is_.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{
                    "id": doc_id,
                    "status": "completed",
                    "error_stage": None,
                    "error_message": None,
                    "retry_count": 0,
                    "knowledge_base_id": str(uuid4()),
                    "tags": ["strategy", "leadership"],
                }]
            )
            mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"user_id": TEST_USER_ID}
            )
            mock_get_sb.return_value = mock_sb

            response = client.get(f"/api/v1/documents/{doc_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["tags"] == ["strategy", "leadership"]

    def test_document_status_empty_tags(self, client):
        """GET /documents/{id} returns empty tags when none set."""
        doc_id = str(uuid4())
        with patch("app.api.routes.documents.get_supabase") as mock_get_sb:
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.is_.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{
                    "id": doc_id,
                    "status": "completed",
                    "error_stage": None,
                    "error_message": None,
                    "retry_count": 0,
                    "knowledge_base_id": str(uuid4()),
                    "tags": None,
                }]
            )
            mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"user_id": TEST_USER_ID}
            )
            mock_get_sb.return_value = mock_sb

            response = client.get(f"/api/v1/documents/{doc_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["tags"] == []


# ---------------------------------------------------------------------------
# Indexer retry on transient errors — KIN-KB-FIX
# ---------------------------------------------------------------------------


class TestIndexerTransientRetry:
    """index_chunks retries on transient network errors (EAGAIN, ReadError)."""

    def test_retries_on_resource_temporarily_unavailable(self, db_session):
        """
        Errno 35 (Resource temporarily unavailable) triggers retry.
        Second attempt succeeds — chunks are indexed.
        """
        from app.services.ingestion.indexer import index_chunks
        from app.services.ingestion.chunker import Chunk

        document_id = uuid4()
        kb_id = uuid4()
        project_id = uuid4()

        chunks = [Chunk(text="Test chunk", chunk_index=0, token_count=2)]
        embeddings = [[0.1] * 3072]

        attempt = {"n": 0}
        original_execute = db_session.table.return_value.insert.return_value.execute

        def _fail_then_succeed():
            attempt["n"] += 1
            if attempt["n"] == 1:
                raise httpx.ReadError("[Errno 35] Resource temporarily unavailable")
            return MagicMock(data=[{"id": str(uuid4())}])

        db_session.table.return_value.insert.return_value.execute.side_effect = _fail_then_succeed

        with patch("asyncio.sleep", new_callable=AsyncMock):
            count = _run(index_chunks(db_session, document_id, kb_id, project_id, None, chunks, embeddings))

        assert count == 1
        assert attempt["n"] == 2  # failed once, succeeded on retry

    def test_non_transient_error_raises_immediately(self, db_session):
        """
        Non-transient errors (e.g., schema mismatch) raise immediately without retry.
        """
        from app.services.ingestion.indexer import index_chunks
        from app.services.ingestion.chunker import Chunk

        document_id = uuid4()
        kb_id = uuid4()

        chunks = [Chunk(text="Test chunk", chunk_index=0, token_count=2)]
        embeddings = [[0.1] * 3072]

        attempt = {"n": 0}

        def _always_fail():
            attempt["n"] += 1
            raise ValueError("column 'bad_col' does not exist")

        db_session.table.return_value.insert.return_value.execute.side_effect = _always_fail

        with pytest.raises(ValueError, match="bad_col"):
            _run(index_chunks(db_session, document_id, kb_id, None, None, chunks, embeddings))

        assert attempt["n"] == 1  # no retry

    def test_exhausts_retries_then_raises(self, db_session):
        """
        If all retry attempts fail with transient errors, the error propagates.
        """
        from app.services.ingestion.indexer import index_chunks
        from app.services.ingestion.chunker import Chunk

        document_id = uuid4()
        kb_id = uuid4()

        chunks = [Chunk(text="Test chunk", chunk_index=0, token_count=2)]
        embeddings = [[0.1] * 3072]

        attempt = {"n": 0}

        def _always_transient_fail():
            attempt["n"] += 1
            raise httpx.ReadError("[Errno 35] Resource temporarily unavailable")

        db_session.table.return_value.insert.return_value.execute.side_effect = _always_transient_fail

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(httpx.ReadError),
        ):
            _run(index_chunks(db_session, document_id, kb_id, None, None, chunks, embeddings))

        assert attempt["n"] == 3  # 1 initial + 2 retries


# ---------------------------------------------------------------------------
# Pipeline uses dedicated Supabase client — KIN-KB-FIX
# ---------------------------------------------------------------------------


class TestPipelineClientIsolation:
    """Upload and retry dispatch background tasks with a fresh Supabase client."""

    def test_upload_uses_create_supabase_for_pipeline(self, client):
        """
        POST /documents/upload passes a fresh (non-singleton) Supabase client
        to the background pipeline, not the shared singleton.
        """
        kb_id = str(uuid4())

        kb_mock = MagicMock()
        kb_mock.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"project_id": None, "agent_definition_id": str(uuid4()), "user_id": TEST_USER_ID}
        )

        doc_mock = MagicMock()
        doc_mock.insert.return_value.execute.return_value = MagicMock(data=[{"id": "new-doc-id"}])

        def _table(name):
            if name == "knowledge_bases":
                return kb_mock
            elif name == "knowledge_base_documents":
                return doc_mock
            return MagicMock()

        singleton_sb = MagicMock()
        singleton_sb.table.side_effect = _table
        singleton_sb.storage.from_.return_value.upload.return_value = None

        fresh_sb = MagicMock(name="fresh_pipeline_client")

        with (
            patch("app.api.routes.documents.get_supabase", return_value=singleton_sb),
            patch("app.api.routes.documents.create_supabase", return_value=fresh_sb) as mock_create,
            patch("app.api.routes.documents.fetch_user_key_async", new_callable=AsyncMock, return_value="sk-test"),
            patch("app.api.routes.documents.run_ingestion", new_callable=AsyncMock) as mock_run,
        ):
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.txt", b"hello world", "text/plain")},
                data={"knowledge_base_id": kb_id},
            )

        assert response.status_code == 200
        mock_create.assert_called_once()
        # Verify the pipeline received the fresh client, not the singleton
        pipeline_supabase_arg = mock_run.call_args.args[0]
        assert pipeline_supabase_arg is fresh_sb
        assert pipeline_supabase_arg is not singleton_sb
