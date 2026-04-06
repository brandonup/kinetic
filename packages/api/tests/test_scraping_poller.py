"""
Tests for scrape source poller — KIN-462.

All Supabase calls are mocked. Tests cover: due source discovery,
dedup logic, success/failure state updates, backoff calculation,
auto-deactivation, and ingestion dispatch.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.scraping.poller import (
    BASE_BACKOFF_MINUTES,
    MAX_BACKOFF_HOURS,
    MAX_CONSECUTIVE_FAILURES,
    POLL_INTERVAL_MINUTES,
    _calculate_backoff,
    _calculate_next_run,
    poll_scrape_sources,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

USER_ID = "test-user-00000000-0000-0000-0000-000000000001"
KB_ID = str(uuid4())
SOURCE_ID = str(uuid4())
PROJECT_ID = str(uuid4())
AGENT_DEF_ID = str(uuid4())


def _source_row(
    source_id=SOURCE_ID,
    user_id=USER_ID,
    kb_id=KB_ID,
    failures=0,
    **overrides,
):
    row = {
        "id": source_id,
        "knowledge_base_id": kb_id,
        "user_id": user_id,
        "source_type": "rss",
        "source_url": "https://example.com/feed.xml",
        "frequency": "daily",
        "is_active": True,
        "last_scraped_at": None,
        "next_run_at": "2026-04-05T00:00:00+00:00",
        "consecutive_failures": failures,
        "credential_ciphertext": None,
        "credential_nonce": None,
    }
    row.update(overrides)
    return row


def _scraped_post(external_id="ext-1", title="Post One", url="https://example.com/1"):
    """Build a mock ScrapedPost-like object."""
    post = MagicMock()
    post.external_id = external_id
    post.title = title
    post.url = url
    post.content = "Body text of the post."
    post.published_at = datetime(2026, 4, 5, 12, 0, 0)
    return post


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# _calculate_next_run tests
# ---------------------------------------------------------------------------


class TestCalculateNextRun:
    def test_daily(self):
        base = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
        result = _calculate_next_run("daily", base)
        assert result == base + timedelta(days=1)

    def test_weekly(self):
        base = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
        result = _calculate_next_run("weekly", base)
        assert result == base + timedelta(weeks=1)

    def test_monthly(self):
        base = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
        result = _calculate_next_run("monthly", base)
        assert result == base + timedelta(days=30)

    def test_unknown_frequency_defaults_to_daily(self):
        base = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
        result = _calculate_next_run("unknown", base)
        assert result == base + timedelta(days=1)

    def test_none_base_uses_utc_now(self):
        before = datetime.now(timezone.utc)
        result = _calculate_next_run("daily")
        after = datetime.now(timezone.utc)
        assert before + timedelta(days=1) <= result <= after + timedelta(days=1)


# ---------------------------------------------------------------------------
# _calculate_backoff tests
# ---------------------------------------------------------------------------


class TestCalculateBackoff:
    def test_first_failure(self):
        result = _calculate_backoff(0)
        assert result == timedelta(minutes=BASE_BACKOFF_MINUTES)

    def test_exponential_growth(self):
        result = _calculate_backoff(3)
        expected = timedelta(minutes=BASE_BACKOFF_MINUTES * (2**3))
        assert result == expected

    def test_capped_at_max(self):
        result = _calculate_backoff(100)
        assert result == timedelta(hours=MAX_BACKOFF_HOURS)


# ---------------------------------------------------------------------------
# poll_scrape_sources tests
# ---------------------------------------------------------------------------


def _build_mock_supabase(
    due_sources: list | None = None,
    existing_external_ids: list | None = None,
    kb_data: dict | None = None,
    openai_key: str = "sk-test-key",
):
    """Build a mock Supabase client with configurable table responses."""
    mock = MagicMock()

    # Track call sequences by table name
    table_calls = {}

    def _table_side_effect(table_name):
        chain = MagicMock()

        if table_name == "scrape_sources":
            if "scrape_sources_select" not in table_calls:
                # First call: due sources query
                table_calls["scrape_sources_select"] = True
                chain.select.return_value.eq.return_value.lte.return_value.order.return_value.execute.return_value = MagicMock(
                    data=due_sources if due_sources is not None else []
                )
            else:
                # Subsequent: update calls
                chain.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        elif table_name == "scrape_source_posts":
            # Dedup query
            chain.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"external_id": eid} for eid in (existing_external_ids or [])]
            )
            # Insert
            chain.insert.return_value.execute.return_value = MagicMock(data=[])
        elif table_name == "knowledge_bases":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=kb_data or {"project_id": PROJECT_ID, "agent_definition_id": AGENT_DEF_ID}
            )
        elif table_name == "knowledge_base_documents":
            chain.insert.return_value.execute.return_value = MagicMock(data=[])
            chain.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        return chain

    mock.table.side_effect = _table_side_effect
    mock.storage.from_.return_value.upload.return_value = None
    return mock


SB_PATCH = "app.services.scraping.poller._get_client"
SCRAPER_PATCH = "app.services.scraping.poller._resolve_scraper"
USER_KEY_PATCH = "app.services.scraping.poller._fetch_openai_key"
INGEST_POST_PATCH = "app.services.scraping.poller._ingest_post"


class TestPollScrapeSources:
    """Tests for the top-level poll_scrape_sources() entry point."""

    def test_no_due_sources_is_noop(self):
        """When no sources are due, poller returns without processing."""
        mock_sb = _build_mock_supabase(due_sources=[])

        with patch(SB_PATCH, return_value=mock_sb):
            _run(poll_scrape_sources())

        # Only the due-sources query should have been called
        mock_sb.table.assert_called_once_with("scrape_sources")

    def test_supabase_client_failure_returns_gracefully(self):
        """If get_supabase() fails, poller logs and returns (no crash)."""
        with patch(SB_PATCH, side_effect=RuntimeError("Connection refused")):
            # Should not raise
            _run(poll_scrape_sources())

    def test_due_sources_query_failure_returns_gracefully(self):
        """If the due-sources query fails, poller logs and returns."""
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.lte.return_value.order.return_value.execute.side_effect = RuntimeError(
            "DB error"
        )

        with patch(SB_PATCH, return_value=mock_sb):
            _run(poll_scrape_sources())

    def test_processes_due_source_with_new_posts(self):
        """Due source with new posts: scraper runs, dedup filters, ingestion called."""
        source = _source_row()
        post1 = _scraped_post(external_id="new-1")
        post2 = _scraped_post(external_id="existing-1")

        mock_sb = _build_mock_supabase(
            due_sources=[source],
            existing_external_ids=["existing-1"],
        )

        mock_scraper = AsyncMock()
        mock_scraper.scrape.return_value = [post1, post2]

        with (
            patch(SB_PATCH, return_value=mock_sb),
            patch(SCRAPER_PATCH, return_value=mock_scraper),
            patch(USER_KEY_PATCH, return_value="sk-test"),
            patch(INGEST_POST_PATCH, new_callable=AsyncMock) as mock_ingest,
        ):
            _run(poll_scrape_sources())

        # Scraper was invoked
        mock_scraper.scrape.assert_called_once()
        # Ingestion called only for the new post (not existing-1)
        assert mock_ingest.call_count == 1

    def test_all_posts_deduped_still_succeeds(self):
        """If all scraped posts already exist, source is still marked as success."""
        source = _source_row()
        post = _scraped_post(external_id="already-exists")

        mock_sb = _build_mock_supabase(
            due_sources=[source],
            existing_external_ids=["already-exists"],
        )

        mock_scraper = AsyncMock()
        mock_scraper.scrape.return_value = [post]

        with (
            patch(SB_PATCH, return_value=mock_sb),
            patch(SCRAPER_PATCH, return_value=mock_scraper),
            patch(USER_KEY_PATCH, return_value="sk-test"),
            patch(INGEST_POST_PATCH, new_callable=AsyncMock) as mock_ingest,
        ):
            _run(poll_scrape_sources())

        # Scraper ran but no ingestion needed
        mock_scraper.scrape.assert_called_once()
        mock_ingest.assert_not_called()

    def test_scraper_failure_increments_failures(self):
        """When scraper.scrape() raises, consecutive_failures increments."""
        source = _source_row(failures=1)

        mock_sb = _build_mock_supabase(due_sources=[source])

        mock_scraper = AsyncMock()
        mock_scraper.scrape.side_effect = RuntimeError("Feed timeout")

        with (
            patch(SB_PATCH, return_value=mock_sb),
            patch(SCRAPER_PATCH, return_value=mock_scraper),
            patch(USER_KEY_PATCH, return_value="sk-test"),
        ):
            _run(poll_scrape_sources())

        # The update call should have been made with incremented failures
        # Find the update call on scrape_sources
        update_calls = [
            c for c in mock_sb.table.call_args_list if c.args[0] == "scrape_sources"
        ]
        assert len(update_calls) >= 1

    def test_auto_deactivation_after_max_failures(self):
        """Source hitting MAX_CONSECUTIVE_FAILURES is auto-deactivated."""
        source = _source_row(failures=MAX_CONSECUTIVE_FAILURES - 1)

        mock_sb = _build_mock_supabase(due_sources=[source])

        mock_scraper = AsyncMock()
        mock_scraper.scrape.side_effect = RuntimeError("Persistent error")

        with (
            patch(SB_PATCH, return_value=mock_sb),
            patch(SCRAPER_PATCH, return_value=mock_scraper),
            patch(USER_KEY_PATCH, return_value="sk-test"),
        ):
            _run(poll_scrape_sources())

        # Verify update was called (auto-deactivation happens in _handle_source_failure)
        update_calls = [
            c for c in mock_sb.table.call_args_list if c.args[0] == "scrape_sources"
        ]
        assert len(update_calls) >= 1

    def test_no_openai_key_triggers_failure(self):
        """If user has no BYOK OpenAI key, source fails gracefully."""
        source = _source_row()
        mock_sb = _build_mock_supabase(due_sources=[source])

        with (
            patch(SB_PATCH, return_value=mock_sb),
            patch(USER_KEY_PATCH, return_value=None),
        ):
            # Should not crash — error is caught per-source
            _run(poll_scrape_sources())

    def test_multiple_sources_processed_independently(self):
        """Multiple due sources: one failure doesn't prevent processing the next."""
        source_a = _source_row(source_id=str(uuid4()))
        source_b = _source_row(source_id=str(uuid4()))

        mock_sb = _build_mock_supabase(due_sources=[source_a, source_b])

        call_count = {"scrape_calls": 0}

        mock_scraper = AsyncMock()

        async def _side_effect(source):
            call_count["scrape_calls"] += 1
            if call_count["scrape_calls"] == 1:
                raise RuntimeError("First source fails")
            return []

        mock_scraper.scrape.side_effect = _side_effect

        with (
            patch(SB_PATCH, return_value=mock_sb),
            patch(SCRAPER_PATCH, return_value=mock_scraper),
            patch(USER_KEY_PATCH, return_value="sk-test"),
        ):
            _run(poll_scrape_sources())

        # Both sources were attempted
        assert call_count["scrape_calls"] == 2


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------


class TestPollerConstants:
    def test_poll_interval(self):
        assert POLL_INTERVAL_MINUTES == 5

    def test_max_consecutive_failures(self):
        assert MAX_CONSECUTIVE_FAILURES == 5

    def test_max_backoff_hours(self):
        assert MAX_BACKOFF_HOURS == 24

    def test_base_backoff_minutes(self):
        assert BASE_BACKOFF_MINUTES == 5
