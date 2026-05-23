"""KIN-481 — `document_date` capture across the three ingestion paths.

Covers:
* helper module (plausibility clamp, datetime→date coercion)
* API upload endpoint — happy path, omitted field, malformed, implausible
* scrape poller `_ingest_post` — published_at mapped, datetime.min coerces to NULL
* document edit (retry) preserves an existing `document_date`

Multi-table mocks use ``side_effect`` routing per the ticket's gotcha note.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID


# ---------------------------------------------------------------------------
# Helper module — pure-function tests (no IO)
# ---------------------------------------------------------------------------


class TestDocumentDateHelpers:
    def test_plausible_date_in_window(self):
        from app.services.ingestion.document_date import is_plausible_document_date

        assert is_plausible_document_date(date(2026, 1, 31)) is True

    def test_pre_2015_is_implausible(self):
        from app.services.ingestion.document_date import is_plausible_document_date

        assert is_plausible_document_date(date(2014, 12, 31)) is False
        assert is_plausible_document_date(date.min) is False

    def test_far_future_is_implausible(self):
        from app.services.ingestion.document_date import is_plausible_document_date

        far_future = datetime.now(timezone.utc).date() + timedelta(days=30)
        assert is_plausible_document_date(far_future) is False

    def test_today_plus_one_is_plausible_boundary(self):
        from app.services.ingestion.document_date import is_plausible_document_date

        boundary = datetime.now(timezone.utc).date() + timedelta(days=1)
        assert is_plausible_document_date(boundary) is True

    def test_coerce_optional_passes_through(self):
        from app.services.ingestion.document_date import coerce_optional_date

        good = date(2026, 1, 1)
        assert coerce_optional_date(good) == good
        assert coerce_optional_date(None) is None
        assert coerce_optional_date(date(1999, 1, 1)) is None

    def test_datetime_min_coerces_to_none(self):
        from app.services.ingestion.document_date import datetime_to_document_date

        # substack.py:_parse_date returns datetime.min on parse failure
        assert datetime_to_document_date(datetime.min) is None

    def test_datetime_to_document_date_truncates(self):
        from app.services.ingestion.document_date import datetime_to_document_date

        dt = datetime(2026, 4, 5, 12, 34, 56, tzinfo=timezone.utc)
        assert datetime_to_document_date(dt) == date(2026, 4, 5)

    def test_datetime_none_returns_none(self):
        from app.services.ingestion.document_date import datetime_to_document_date

        assert datetime_to_document_date(None) is None


# ---------------------------------------------------------------------------
# API upload endpoint — POST /api/v1/documents/upload
# ---------------------------------------------------------------------------


def _kb_and_doc_mocks(kb_user_id: str = TEST_USER_ID):
    """Build shared kb/doc table mocks and the table() router callable.

    Returns ``(kb_mock, doc_mock, table_router)``. The doc insert mock captures
    the row payload so tests can assert on what would have been written.
    """
    kb_mock = MagicMock()
    kb_mock.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"project_id": None, "agent_definition_id": str(uuid4()), "user_id": kb_user_id}
    )

    doc_mock = MagicMock()
    doc_mock.insert.return_value.execute.return_value = MagicMock(data=[{"id": "new-doc-id"}])

    def _table(name: str):
        if name == "knowledge_bases":
            return kb_mock
        if name == "knowledge_base_documents":
            return doc_mock
        return MagicMock()

    return kb_mock, doc_mock, _table


class TestUploadEndpointDocumentDate:
    def test_upload_with_document_date_persists_iso_string(self, client):
        """A valid `document_date` form field appears in the INSERT payload as YYYY-MM-DD."""
        kb_id = str(uuid4())
        _, doc_mock, table_router = _kb_and_doc_mocks()

        with (
            patch("app.api.routes.documents.get_supabase") as mock_get_sb,
            patch("app.api.routes.documents.create_supabase") as mock_create_sb,
            patch(
                "app.api.routes.documents.fetch_user_key_async",
                new_callable=AsyncMock, return_value=None,
            ),
            patch("app.api.routes.documents.run_ingestion", new_callable=AsyncMock),
        ):
            mock_sb = MagicMock()
            mock_sb.table.side_effect = table_router
            mock_sb.storage.from_.return_value.upload.return_value = None
            mock_get_sb.return_value = mock_sb
            mock_create_sb.return_value = MagicMock(name="fresh-sb")

            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.txt", b"hello world", "text/plain")},
                data={"knowledge_base_id": kb_id, "document_date": "2026-01-31"},
            )

        assert response.status_code == 200, response.text
        inserted_row = doc_mock.insert.call_args.args[0]
        assert inserted_row.get("document_date") == "2026-01-31"

    def test_upload_without_document_date_omits_field(self, client):
        """Missing `document_date` form field → the column is not in the INSERT (defaults to NULL)."""
        kb_id = str(uuid4())
        _, doc_mock, table_router = _kb_and_doc_mocks()

        with (
            patch("app.api.routes.documents.get_supabase") as mock_get_sb,
            patch("app.api.routes.documents.create_supabase") as mock_create_sb,
            patch(
                "app.api.routes.documents.fetch_user_key_async",
                new_callable=AsyncMock, return_value=None,
            ),
            patch("app.api.routes.documents.run_ingestion", new_callable=AsyncMock),
        ):
            mock_sb = MagicMock()
            mock_sb.table.side_effect = table_router
            mock_sb.storage.from_.return_value.upload.return_value = None
            mock_get_sb.return_value = mock_sb
            mock_create_sb.return_value = MagicMock(name="fresh-sb")

            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.txt", b"hello world", "text/plain")},
                data={"knowledge_base_id": kb_id},
            )

        assert response.status_code == 200, response.text
        inserted_row = doc_mock.insert.call_args.args[0]
        assert "document_date" not in inserted_row

    def test_upload_with_malformed_document_date_returns_422(self, client):
        """A non-ISO `document_date` returns 422 from FastAPI's form parsing — never 500."""
        kb_id = str(uuid4())
        _, doc_mock, table_router = _kb_and_doc_mocks()

        with patch("app.api.routes.documents.get_supabase") as mock_get_sb:
            mock_sb = MagicMock()
            mock_sb.table.side_effect = table_router
            mock_get_sb.return_value = mock_sb

            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.txt", b"x", "text/plain")},
                data={"knowledge_base_id": kb_id, "document_date": "not-a-date"},
            )

        assert response.status_code == 422
        # INSERT must not have happened on a 422
        doc_mock.insert.assert_not_called()

    def test_upload_with_implausibly_old_date_returns_422(self, client):
        """A parseable but pre-2015 date is rejected with 422 — never 500."""
        kb_id = str(uuid4())
        _, doc_mock, table_router = _kb_and_doc_mocks()

        with patch("app.api.routes.documents.get_supabase") as mock_get_sb:
            mock_sb = MagicMock()
            mock_sb.table.side_effect = table_router
            mock_get_sb.return_value = mock_sb

            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.txt", b"x", "text/plain")},
                data={"knowledge_base_id": kb_id, "document_date": "1999-01-01"},
            )

        assert response.status_code == 422
        doc_mock.insert.assert_not_called()

    def test_upload_with_far_future_date_returns_422(self, client):
        """A date beyond today+1d is rejected with 422."""
        kb_id = str(uuid4())
        _, doc_mock, table_router = _kb_and_doc_mocks()
        far_future = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()

        with patch("app.api.routes.documents.get_supabase") as mock_get_sb:
            mock_sb = MagicMock()
            mock_sb.table.side_effect = table_router
            mock_get_sb.return_value = mock_sb

            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.txt", b"x", "text/plain")},
                data={"knowledge_base_id": kb_id, "document_date": far_future},
            )

        assert response.status_code == 422
        doc_mock.insert.assert_not_called()


# ---------------------------------------------------------------------------
# Scrape poller — _ingest_post
# ---------------------------------------------------------------------------


def _make_post(*, published_at, title="A post", external_id="ext-1", url="https://x/y", content="body"):
    """Construct a minimal ScrapedPost-shaped object."""
    post = MagicMock()
    post.title = title
    post.external_id = external_id
    post.url = url
    post.content = content
    post.published_at = published_at
    return post


class TestPollerIngestPostDocumentDate:
    def _build_supabase(self):
        """Return ``(sb, docs_insert_mock)``."""
        sb = MagicMock()
        docs_table = MagicMock()
        docs_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "x"}])
        scraped_table = MagicMock()
        scraped_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "y"}])

        def _table(name: str):
            if name == "knowledge_base_documents":
                return docs_table
            if name == "scrape_source_posts":
                return scraped_table
            return MagicMock()

        sb.table.side_effect = _table
        sb.storage.from_.return_value.upload.return_value = None
        return sb, docs_table

    @pytest.mark.asyncio
    async def test_ingest_post_maps_published_at_to_document_date(self):
        from app.services.scraping.poller import _ingest_post

        sb, docs_table = self._build_supabase()
        loop = asyncio.get_running_loop()
        published_at = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
        post = _make_post(published_at=published_at)

        with patch(
            "app.services.scraping.poller._dispatch_ingestion",
            new_callable=AsyncMock,
        ):
            await _ingest_post(
                sb, loop,
                source_id="src-1",
                user_id=TEST_USER_ID,
                kb_id="kb-1",
                project_id=None,
                agent_definition_id=None,
                post=post,
            )

        inserted_row = docs_table.insert.call_args.args[0]
        assert inserted_row.get("document_date") == "2026-04-05"

    @pytest.mark.asyncio
    async def test_ingest_post_datetime_min_omits_document_date(self):
        """`datetime.min` (substack parse-failure sentinel) → document_date omitted from INSERT."""
        from app.services.scraping.poller import _ingest_post

        sb, docs_table = self._build_supabase()
        loop = asyncio.get_running_loop()
        post = _make_post(published_at=datetime.min)

        with patch(
            "app.services.scraping.poller._dispatch_ingestion",
            new_callable=AsyncMock,
        ):
            await _ingest_post(
                sb, loop,
                source_id="src-1",
                user_id=TEST_USER_ID,
                kb_id="kb-1",
                project_id=None,
                agent_definition_id=None,
                post=post,
            )

        inserted_row = docs_table.insert.call_args.args[0]
        assert "document_date" not in inserted_row


# ---------------------------------------------------------------------------
# Retry / re-ingest preserves document_date
# ---------------------------------------------------------------------------


class TestRetryPreservesDocumentDate:
    """The retry endpoint resets status fields but must not clobber document_date."""

    def test_retry_update_does_not_include_document_date(self, client):
        """POST /documents/{id}/retry's reset update touches status fields only — document_date is left alone."""
        kb_id = str(uuid4())
        doc_id = str(uuid4())

        doc_mock = MagicMock()
        # initial fetch
        doc_mock.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": doc_id,
                "status": "failed",
                "error_stage": "extracting",
                "storage_uri": f"{doc_id}/foo.txt",
                "knowledge_base_id": kb_id,
                "file_type": "text/plain",
                "title": "foo.txt",
            }
        )
        # atomic reset
        update_chain = doc_mock.update.return_value.eq.return_value.eq.return_value.execute
        update_chain.return_value = MagicMock(data=[{"id": doc_id}])

        kb_mock = MagicMock()
        kb_mock.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "user_id": TEST_USER_ID,
                "project_id": None,
                "agent_definition_id": str(uuid4()),
            }
        )

        chunks_mock = MagicMock()
        chunks_mock.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        def _table(name: str):
            if name == "knowledge_base_documents":
                return doc_mock
            if name == "knowledge_bases":
                return kb_mock
            if name == "knowledge_base_chunks":
                return chunks_mock
            return MagicMock()

        with (
            patch("app.api.routes.documents.get_supabase") as mock_get_sb,
            patch("app.api.routes.documents.create_supabase") as mock_create_sb,
            patch(
                "app.api.routes.documents.fetch_user_key_async",
                new_callable=AsyncMock, return_value=None,
            ),
            patch("app.api.routes.documents.run_ingestion_from_stage", new_callable=AsyncMock),
        ):
            mock_sb = MagicMock()
            mock_sb.table.side_effect = _table
            mock_sb.storage.from_.return_value.download.return_value = b"hello"
            mock_get_sb.return_value = mock_sb
            mock_create_sb.return_value = MagicMock(name="fresh-sb")

            response = client.post(f"/api/v1/documents/{doc_id}/retry")

        assert response.status_code == 200, response.text
        # The atomic reset update payload should be status + error fields only
        update_payload = doc_mock.update.call_args.args[0]
        assert "document_date" not in update_payload, (
            "Retry must never reset document_date — it represents the article's "
            "real publication date, not a per-ingest field."
        )


# ---------------------------------------------------------------------------
# nbj_extractor bulk uploader — convert helper
# ---------------------------------------------------------------------------


class TestBulkUploaderExtractDocumentDate:
    def _import_extract(self):
        # The script lives outside the API package; load it directly so we don't
        # depend on its CWD or env (no requests/JWT needed for these helpers).
        import importlib.util
        from pathlib import Path

        script = Path(__file__).resolve().parents[3] / "nbj_extractor" / "bulk_upload_to_kb.py"
        spec = importlib.util.spec_from_file_location("bulk_upload_to_kb", script)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.extract_document_date

    def test_truncates_iso_timestamp_to_date(self):
        extract = self._import_extract()
        assert extract({"date": "2026-01-31T03:58:51.677Z"}) == "2026-01-31"

    def test_handles_date_without_timezone(self):
        extract = self._import_extract()
        assert extract({"date": "2026-01-31T03:58:51"}) == "2026-01-31"

    def test_missing_date_field_returns_none(self):
        extract = self._import_extract()
        assert extract({}) is None
        assert extract({"date": ""}) is None
        assert extract({"date": None}) is None

    def test_unparseable_date_returns_none(self):
        extract = self._import_extract()
        assert extract({"date": "not-a-date"}) is None
        assert extract({"date": 12345}) is None  # wrong type
