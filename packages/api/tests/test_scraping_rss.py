"""
Tests for RSSFeedScraper and scraper registry — KIN-461.

feedparser.parse is mocked to return pre-built feed objects.
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.scraping.base import ScraperError, ScrapeSource
from app.services.scraping.registry import SCRAPER_REGISTRY, get_scraper
from app.services.scraping.rss import RSSFeedScraper, _strip_html
from app.services.scraping.substack import SubstackScraper


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SOURCE = ScrapeSource(
    id="src-rss-1",
    knowledge_base_id="kb-1",
    user_id="user-1",
    source_type="rss",
    source_url="https://example.com/feed.xml",
    frequency="daily",
    next_run_at=datetime(2026, 4, 5),
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_entry(
    entry_id: str = "entry-1",
    title: str = "Test Entry",
    link: str = "https://example.com/post/1",
    content_html: str = "<p>Full content here.</p>",
    summary: str = "Summary fallback.",
    published_parsed: tuple | None = (2026, 3, 15, 12, 0, 0, 0, 0, 0),
    use_content: bool = True,
):
    """Build a mock feedparser entry."""
    entry = MagicMock()
    entry.get = lambda k, d=None: {
        "id": entry_id,
        "guid": entry_id,
        "title": title,
        "link": link,
        "content": [{"value": content_html}] if use_content else [],
        "summary": summary,
        "published_parsed": published_parsed,
        "updated_parsed": None,
        "published": "",
        "updated": "",
    }.get(k, d)
    return entry


def _make_feed(entries: list, bozo: bool = False, bozo_exception=None):
    """Build a mock feedparser result."""
    feed = MagicMock()
    feed.entries = entries
    feed.bozo = 1 if bozo else 0
    feed.get = lambda k, d=None: {"bozo_exception": bozo_exception}.get(k, d)
    return feed


# ---------------------------------------------------------------------------
# RSSFeedScraper tests
# ---------------------------------------------------------------------------


class TestRSSFeedScraperHappyPath:
    def test_multiple_entries(self):
        """Feed with 2 entries → 2 ScrapedPost results."""
        entries = [
            _make_entry(entry_id="e1", title="Post One", link="https://example.com/1"),
            _make_entry(entry_id="e2", title="Post Two", link="https://example.com/2"),
        ]
        feed = _make_feed(entries)
        scraper = RSSFeedScraper()

        with patch("app.services.scraping.rss.feedparser") as mock_fp:
            mock_fp.parse.return_value = feed
            results = _run(scraper.scrape(SOURCE))

        assert len(results) == 2
        assert results[0].external_id == "e1"
        assert results[0].title == "Post One"
        assert results[1].external_id == "e2"

    def test_atom_feed(self):
        """Atom feed entry with content[0].value → uses full content."""
        entry = _make_entry(
            entry_id="atom-1",
            content_html="<div>Atom content body</div>",
            use_content=True,
        )
        feed = _make_feed([entry])
        scraper = RSSFeedScraper()

        with patch("app.services.scraping.rss.feedparser") as mock_fp:
            mock_fp.parse.return_value = feed
            results = _run(scraper.scrape(SOURCE))

        assert len(results) == 1
        assert "Atom content body" in results[0].content

    def test_date_parsed_correctly(self):
        """published_parsed tuple → datetime conversion."""
        entry = _make_entry(published_parsed=(2026, 1, 15, 10, 30, 0, 0, 0, 0))
        feed = _make_feed([entry])
        scraper = RSSFeedScraper()

        with patch("app.services.scraping.rss.feedparser") as mock_fp:
            mock_fp.parse.return_value = feed
            results = _run(scraper.scrape(SOURCE))

        assert results[0].published_at == datetime(2026, 1, 15, 10, 30, 0)


class TestRSSFeedScraperFallback:
    def test_empty_content_falls_back_to_summary(self):
        """Entry with no content → falls back to summary."""
        entry = _make_entry(
            use_content=False,
            summary="<p>This is the summary.</p>",
        )
        feed = _make_feed([entry])
        scraper = RSSFeedScraper()

        with patch("app.services.scraping.rss.feedparser") as mock_fp:
            mock_fp.parse.return_value = feed
            results = _run(scraper.scrape(SOURCE))

        assert len(results) == 1
        assert "This is the summary" in results[0].content

    def test_empty_feed_returns_empty(self):
        """Feed with no entries → empty list."""
        feed = _make_feed([])
        scraper = RSSFeedScraper()

        with patch("app.services.scraping.rss.feedparser") as mock_fp:
            mock_fp.parse.return_value = feed
            results = _run(scraper.scrape(SOURCE))

        assert results == []


class TestRSSFeedScraperErrors:
    def test_malformed_feed_raises_scraper_error(self):
        """Malformed feed (bozo=1, no entries) → ScraperError."""
        feed = _make_feed([], bozo=True, bozo_exception="XML parse error")
        scraper = RSSFeedScraper()

        with patch("app.services.scraping.rss.feedparser") as mock_fp:
            mock_fp.parse.return_value = feed
            with pytest.raises(ScraperError, match="Malformed feed"):
                _run(scraper.scrape(SOURCE))

    def test_parse_exception_raises_scraper_error(self):
        """feedparser.parse raises → ScraperError."""
        scraper = RSSFeedScraper()

        with patch("app.services.scraping.rss.feedparser") as mock_fp:
            mock_fp.parse.side_effect = RuntimeError("Network error")
            with pytest.raises(ScraperError, match="Failed to parse"):
                _run(scraper.scrape(SOURCE))


# ---------------------------------------------------------------------------
# Strip HTML tests
# ---------------------------------------------------------------------------


class TestStripHtml:
    def test_basic_html(self):
        assert "Hello world" in _strip_html("<p>Hello <b>world</b></p>")

    def test_empty_html(self):
        assert _strip_html("") == ""
        assert _strip_html(None) == ""


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestScraperRegistry:
    def test_get_substack_scraper(self):
        scraper = get_scraper("substack")
        assert isinstance(scraper, SubstackScraper)

    def test_get_rss_scraper(self):
        scraper = get_scraper("rss")
        assert isinstance(scraper, RSSFeedScraper)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown scraper source_type"):
            get_scraper("unknown_type")

    def test_registry_has_all_types(self):
        assert "substack" in SCRAPER_REGISTRY
        assert "rss" in SCRAPER_REGISTRY
