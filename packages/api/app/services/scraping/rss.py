"""
RSSFeedScraper — KIN-461.

Parses RSS/Atom feeds via feedparser and returns ScrapedPost instances.
No authentication required — RSS feeds are public.

Design doc: docs/plans/2026-04-05-scheduled-kb-scraping-design.md § Scraper Architecture.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

from app.services.scraping.base import (
    BaseScraper,
    ScrapedPost,
    ScrapeSource,
    ScraperError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------


def _strip_html(html: str) -> str:
    """Strip HTML tags and return clean plain text."""
    if not html:
        return ""

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# ---------------------------------------------------------------------------
# RSSFeedScraper
# ---------------------------------------------------------------------------


class RSSFeedScraper(BaseScraper):
    """Scrapes posts from an RSS or Atom feed.

    Uses feedparser to parse the feed XML. Extracts entry content
    (prefers `content[0].value`, falls back to `summary`), strips HTML,
    and returns ScrapedPost instances.
    """

    async def scrape(self, source: ScrapeSource) -> list[ScrapedPost]:
        """Fetch and parse an RSS/Atom feed.

        Args:
            source: ScrapeSource with source_url pointing to the feed URL.
                    Credentials are ignored (RSS feeds are public).

        Returns:
            List of ScrapedPost instances.

        Raises:
            ScraperError: On feed fetch/parse failures.
        """
        import feedparser

        feed_url = source.source_url.strip()

        try:
            feed = feedparser.parse(feed_url)
        except Exception as exc:
            raise ScraperError(f"Failed to parse feed at {feed_url}: {exc}") from exc

        # feedparser sets bozo=1 for malformed feeds
        if feed.bozo and not feed.entries:
            exc = feed.get("bozo_exception", "Unknown parse error")
            raise ScraperError(f"Malformed feed at {feed_url}: {exc}")

        if not feed.entries:
            logger.info("No entries found in feed at %s", feed_url)
            return []

        results: list[ScrapedPost] = []
        for entry in feed.entries:
            external_id = self._extract_id(entry)
            if not external_id:
                logger.warning("Skipping entry with no id/guid in feed %s", feed_url)
                continue

            content_html = self._extract_content(entry)
            content = _strip_html(content_html)

            title = (entry.get("title") or "").strip()
            url = (entry.get("link") or "").strip()
            published_at = self._parse_date(entry)

            results.append(
                ScrapedPost(
                    external_id=external_id,
                    title=title,
                    url=url,
                    content=content,
                    published_at=published_at,
                )
            )

        logger.info("Parsed %d entries from feed %s", len(results), feed_url)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_id(entry) -> str | None:
        """Extract entry ID: prefer `id`, fall back to `guid`, then `link`."""
        return (
            entry.get("id")
            or entry.get("guid")
            or entry.get("link")
            or None
        )

    @staticmethod
    def _extract_content(entry) -> str:
        """Extract entry content HTML.

        Prefers `content[0].value` (full content), falls back to `summary`.
        """
        # content field (RSS 1.0 / Atom)
        content_list = entry.get("content", [])
        if content_list and isinstance(content_list, list):
            value = content_list[0].get("value", "")
            if value:
                return value

        # summary field (RSS 2.0 <description>)
        summary = entry.get("summary", "")
        if summary:
            return summary

        return ""

    @staticmethod
    def _parse_date(entry) -> datetime:
        """Parse entry published date from feedparser's normalized fields."""
        # feedparser normalizes dates into published_parsed (time.struct_time)
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            try:
                return datetime(*parsed[:6])
            except (TypeError, ValueError):
                pass

        # Try raw date string
        date_str = entry.get("published") or entry.get("updated") or ""
        if date_str:
            try:
                return parsedate_to_datetime(date_str)
            except (TypeError, ValueError):
                pass
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return datetime.min
