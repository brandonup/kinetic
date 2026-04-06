"""
SubstackScraper — KIN-460.

Refactored from nbj_extractor/substack_scraper.py into a pluggable
scraper class. Core logic extracted; CLI-specific parts removed.

Uses httpx (already a project dependency) for async HTTP.

Design doc: docs/plans/2026-04-05-scheduled-kb-scraping-design.md § Scraper Architecture.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import unquote

import httpx

from app.services.scraping.base import (
    BaseScraper,
    ScrapedPost,
    ScrapeSource,
    ScraperAuthError,
    ScraperError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUEST_TIMEOUT = 15        # seconds
REQUEST_DELAY = 0.75        # seconds between paginated requests
PAGE_SIZE = 25              # Substack API page size
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko)"
)


# ---------------------------------------------------------------------------
# HTML → plain text
# ---------------------------------------------------------------------------


def _html_to_text(html_content: str) -> str:
    """Convert HTML to clean plain text suitable for RAG ingestion."""
    if not html_content:
        return ""

    import html2text

    h = html2text.HTML2Text()
    h.ignore_links = False       # keep links as [text](url) for citations
    h.ignore_images = True
    h.ignore_emphasis = False
    h.body_width = 0             # don't wrap lines
    h.protect_links = True

    text = h.handle(html_content)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # Remove trailing Substack CDN image links
    text = re.sub(r"\[]\(https://substackcdn\.com[^)]*\)\s*$", "", text).strip()
    return text


def _extract_body_html_from_page(page_html: str) -> str | None:
    """Extract post body HTML from a rendered Substack page.

    Tries multiple CSS selectors in order of specificity.
    Removes paywall CTAs if present.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_html, "html.parser")
    body_el = (
        soup.select_one("div.available-content")
        or soup.select_one("div.body.markup")
        or soup.select_one("div.post-content")
        or soup.select_one("article .body")
    )
    if not body_el:
        return None

    # Remove paywall CTA elements
    for cta in body_el.select(".paywall, .subscription-widget-wrap, .paywall-jump"):
        cta.decompose()

    return str(body_el)


# ---------------------------------------------------------------------------
# SubstackScraper
# ---------------------------------------------------------------------------


class SubstackScraper(BaseScraper):
    """Scrapes posts from a Substack newsletter.

    Fetches post metadata via the Substack API (/api/v1/posts),
    then loads full HTML for paid content via /p/{slug} with a session cookie.
    Falls back to API content if the page fetch fails.
    """

    async def scrape(self, source: ScrapeSource) -> list[ScrapedPost]:
        """Fetch all posts from a Substack newsletter.

        Args:
            source: ScrapeSource with source_url (Substack base URL)
                    and optional credential (session cookie for paid content).

        Returns:
            List of ScrapedPost instances.

        Raises:
            ScraperAuthError: On HTTP 403 (expired/invalid cookie).
            ScraperError: On other HTTP or parsing failures.
        """
        base_url = source.source_url.rstrip("/")
        headers = self._build_headers(source.credential)

        async with httpx.AsyncClient(
            headers=headers, timeout=REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            # Step 1: Fetch post list with pagination
            post_metas = await self._fetch_post_list(client, base_url)

            if not post_metas:
                logger.info("No posts found at %s", base_url)
                return []

            # Step 2: Fetch full content for each post
            results: list[ScrapedPost] = []
            for meta in post_metas:
                slug = meta.get("slug", "")
                if not slug:
                    continue

                body_html = await self._fetch_post_content(
                    client, base_url, slug, meta
                )
                content = _html_to_text(body_html) if body_html else ""

                # Fall back to truncated body text from API metadata
                if not content:
                    content = meta.get("truncated_body_text", "") or ""

                published_at = self._parse_date(meta.get("post_date", ""))

                results.append(
                    ScrapedPost(
                        external_id=str(meta.get("id", "")),
                        title=(meta.get("title") or "").strip(),
                        url=meta.get("canonical_url", ""),
                        content=content,
                        published_at=published_at,
                    )
                )

            logger.info("Scraped %d posts from %s", len(results), base_url)
            return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_headers(credential: str | None) -> dict[str, str]:
        """Build HTTP headers with optional session cookie."""
        headers: dict[str, str] = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if credential:
            decoded = unquote(credential)
            headers["Cookie"] = f"substack.sid={decoded}"
        return headers

    async def _fetch_post_list(
        self, client: httpx.AsyncClient, base_url: str
    ) -> list[dict]:
        """Fetch all post metadata via paginated Substack API."""
        posts: list[dict] = []
        offset = 0

        while True:
            url = f"{base_url}/api/v1/posts"
            try:
                resp = await client.get(
                    url, params={"limit": PAGE_SIZE, "offset": offset}
                )
                if resp.status_code == 403:
                    raise ScraperAuthError(
                        f"HTTP 403 fetching post list — session cookie may be expired"
                    )
                resp.raise_for_status()
                batch = resp.json()
            except ScraperAuthError:
                raise
            except httpx.HTTPStatusError as exc:
                raise ScraperError(
                    f"HTTP {exc.response.status_code} fetching post list from {base_url}"
                ) from exc
            except Exception as exc:
                raise ScraperError(
                    f"Error fetching post list from {base_url}: {exc}"
                ) from exc

            if not batch or not isinstance(batch, list):
                break

            posts.extend(batch)

            if len(batch) < PAGE_SIZE:
                break  # last page

            offset += PAGE_SIZE

        return posts

    async def _fetch_post_content(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        slug: str,
        meta: dict,
    ) -> str:
        """Fetch full post body HTML.

        Strategy:
        1. Try the rendered page (/p/{slug}) — includes full paid content
        2. Fall back to API body_html from metadata
        """
        # Try rendered page first (full content including paid)
        page_url = f"{base_url}/p/{slug}"
        try:
            resp = await client.get(
                page_url, headers={"Accept": "text/html"}
            )
            if resp.status_code == 403:
                logger.warning(
                    "HTTP 403 for page %s — cookie may be expired, falling back to API",
                    slug,
                )
            elif resp.is_success:
                body_html = _extract_body_html_from_page(resp.text)
                if body_html:
                    return body_html
        except Exception as exc:
            logger.warning("Page fetch failed for %s: %s", slug, exc)

        # Fallback: use body_html from metadata (may be truncated for paid)
        return meta.get("body_html", "") or ""

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse a Substack date string to datetime."""
        if not date_str:
            return datetime.min

        # Substack uses ISO 8601 format
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Last resort: try fromisoformat
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            logger.warning("Unparseable date: %s", date_str)
            return datetime.min
