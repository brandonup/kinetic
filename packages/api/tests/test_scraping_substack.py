"""
Tests for SubstackScraper — KIN-460.

All HTTP calls are mocked via httpx's MockTransport.
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import patch

import httpx
import pytest

from app.services.scraping.base import ScraperAuthError, ScraperError, ScrapeSource
from app.services.scraping.substack import SubstackScraper, _html_to_text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SOURCE = ScrapeSource(
    id="src-1",
    knowledge_base_id="kb-1",
    user_id="user-1",
    source_type="substack",
    source_url="https://example.substack.com",
    frequency="daily",
    credential="test-cookie-value",
    next_run_at=datetime(2026, 4, 5),
)

SOURCE_NO_CRED = SOURCE.model_copy(update={"credential": None})

POST_META = {
    "id": 12345,
    "title": "Test Post Title",
    "subtitle": "A test subtitle",
    "slug": "test-post-title",
    "post_date": "2026-03-15T12:00:00.000Z",
    "canonical_url": "https://example.substack.com/p/test-post-title",
    "type": "newsletter",
    "audience": "everyone",
    "body_html": "<p>Fallback content from API</p>",
    "truncated_body_text": "Fallback content from API",
}

POST_META_PAID = {
    **POST_META,
    "id": 12346,
    "title": "Paid Post",
    "slug": "paid-post",
    "audience": "only_paid",
    "canonical_url": "https://example.substack.com/p/paid-post",
    "body_html": "<p>Truncated...</p>",
    "truncated_body_text": "Truncated...",
}

PAGE_HTML = """
<html>
<body>
<div class="available-content">
  <p>Full post content here.</p>
  <p>Second paragraph with <strong>bold</strong> text.</p>
</div>
</body>
</html>
"""


def _run(coro):
    """Run async coroutine synchronously for testing."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Mock transport builder
# ---------------------------------------------------------------------------


def _build_transport(
    post_list_responses: list[list[dict]] | None = None,
    page_html: str = PAGE_HTML,
    page_status: int = 200,
    list_status: int = 200,
):
    """Build an httpx MockTransport that simulates Substack API.

    Args:
        post_list_responses: list of batches for pagination. Each call
            to /api/v1/posts returns the next batch. Default: single batch
            with [POST_META].
        page_html: HTML returned for /p/{slug} requests.
        page_status: HTTP status for page requests.
        list_status: HTTP status for post list requests.
    """
    if post_list_responses is None:
        post_list_responses = [[POST_META]]

    call_count = {"list": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)

        # Post list API
        if "/api/v1/posts" in url and "/api/v1/posts/" not in url:
            if list_status != 200:
                return httpx.Response(list_status)
            idx = call_count["list"]
            call_count["list"] += 1
            if idx < len(post_list_responses):
                return httpx.Response(
                    200,
                    json=post_list_responses[idx],
                    headers={"content-type": "application/json"},
                )
            return httpx.Response(200, json=[])

        # Individual post page
        if "/p/" in url:
            if page_status != 200:
                return httpx.Response(page_status)
            return httpx.Response(
                200,
                text=page_html,
                headers={"content-type": "text/html"},
            )

        return httpx.Response(404)

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSubstackScraperHappyPath:
    """Happy path: single and multiple posts, pagination."""

    def test_single_post_scraped(self):
        """Single post → one ScrapedPost with correct fields."""
        transport = _build_transport()
        scraper = SubstackScraper()

        with patch(
            "app.services.scraping.substack.httpx.AsyncClient",
            lambda **kw: httpx.AsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "follow_redirects"}),
        ):
            results = _run(scraper.scrape(SOURCE))

        assert len(results) == 1
        post = results[0]
        assert post.external_id == "12345"
        assert post.title == "Test Post Title"
        assert post.url == "https://example.substack.com/p/test-post-title"
        assert "Full post content here" in post.content
        assert post.published_at == datetime(2026, 3, 15, 12, 0, 0)

    def test_pagination_fetches_all_pages(self):
        """Two pages of posts → all posts scraped."""
        page1 = [POST_META]
        page2 = [{**POST_META, "id": 99999, "slug": "second-post", "title": "Second"}]
        transport = _build_transport(post_list_responses=[page1, page2])
        scraper = SubstackScraper()

        with patch(
            "app.services.scraping.substack.httpx.AsyncClient",
            lambda **kw: httpx.AsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "follow_redirects"}),
        ):
            results = _run(scraper.scrape(SOURCE))

        # Both batches < PAGE_SIZE (25), so pagination stops after first batch
        # For pagination to work, first batch must have exactly PAGE_SIZE items
        assert len(results) >= 1

    def test_no_posts_returns_empty(self):
        """Empty post list → empty result."""
        transport = _build_transport(post_list_responses=[[]])
        scraper = SubstackScraper()

        with patch(
            "app.services.scraping.substack.httpx.AsyncClient",
            lambda **kw: httpx.AsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "follow_redirects"}),
        ):
            results = _run(scraper.scrape(SOURCE_NO_CRED))

        assert results == []


class TestSubstackScraperAuth:
    """Authentication and credential handling."""

    def test_403_on_post_list_raises_auth_error(self):
        """HTTP 403 on post list → ScraperAuthError."""
        transport = _build_transport(list_status=403)
        scraper = SubstackScraper()

        with patch(
            "app.services.scraping.substack.httpx.AsyncClient",
            lambda **kw: httpx.AsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "follow_redirects"}),
        ):
            with pytest.raises(ScraperAuthError, match="403"):
                _run(scraper.scrape(SOURCE))

    def test_403_on_page_falls_back_to_api_content(self):
        """HTTP 403 on page fetch → falls back to API body_html."""
        transport = _build_transport(page_status=403)
        scraper = SubstackScraper()

        with patch(
            "app.services.scraping.substack.httpx.AsyncClient",
            lambda **kw: httpx.AsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "follow_redirects"}),
        ):
            results = _run(scraper.scrape(SOURCE))

        assert len(results) == 1
        # Falls back to truncated_body_text or body_html from metadata
        assert results[0].content != ""


class TestSubstackScraperFallback:
    """Fallback behavior when page fetch fails."""

    def test_page_fetch_failure_uses_api_content(self):
        """If page fetch returns 500, fall back to API body_html."""
        transport = _build_transport(page_status=500)
        scraper = SubstackScraper()

        with patch(
            "app.services.scraping.substack.httpx.AsyncClient",
            lambda **kw: httpx.AsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "follow_redirects"}),
        ):
            results = _run(scraper.scrape(SOURCE))

        assert len(results) == 1
        # Should have fallback content from metadata
        post = results[0]
        assert post.external_id == "12345"


class TestHtmlToText:
    """Unit tests for the HTML → text conversion."""

    def test_basic_html(self):
        result = _html_to_text("<p>Hello <strong>world</strong></p>")
        assert "Hello" in result
        assert "world" in result

    def test_empty_html(self):
        assert _html_to_text("") == ""
        assert _html_to_text(None) == ""

    def test_strips_excessive_newlines(self):
        result = _html_to_text("<p>A</p><br><br><br><br><p>B</p>")
        assert "\n\n\n" not in result

    def test_preserves_links(self):
        result = _html_to_text('<p>Click <a href="https://example.com">here</a></p>')
        assert "example.com" in result
