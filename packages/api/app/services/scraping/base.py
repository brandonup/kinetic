"""
Scraper base interface — KIN-460.

Defines the pluggable scraper interface and shared data models.
Design doc: docs/plans/2026-04-05-scheduled-kb-scraping-design.md § Scraper Architecture.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ScrapedPost:
    """A single scraped post, ready for ingestion into the KB pipeline."""

    external_id: str          # Substack post ID or RSS entry GUID
    title: str
    url: str
    content: str              # Clean plain text
    published_at: datetime


class ScrapeSource(BaseModel):
    """Pydantic model matching the scrape_sources DB row.

    The credential field is the *decrypted* plaintext (not raw bytea).
    Decryption happens at the service layer before constructing this model.
    """

    id: str
    knowledge_base_id: str
    user_id: str
    source_type: str          # "substack" | "rss"
    source_url: str
    frequency: str            # "daily" | "weekly" | "monthly"
    credential: Optional[str] = None   # Decrypted cookie/token, None for public
    is_active: bool = True
    last_scraped_at: Optional[datetime] = None
    next_run_at: datetime
    consecutive_failures: int = 0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ScraperError(Exception):
    """Base exception for scraper failures."""


class ScraperAuthError(ScraperError):
    """Raised when authentication fails (expired cookie, invalid token)."""


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseScraper(ABC):
    """Abstract base class for content scrapers.

    Each scraper implementation handles one source_type (e.g., "substack", "rss").
    The scrape() method fetches new posts and returns them as ScrapedPost instances.
    Deduplication (checking which posts are already ingested) is handled by the caller.
    """

    @abstractmethod
    async def scrape(self, source: ScrapeSource) -> list[ScrapedPost]:
        """Fetch posts from the source.

        Args:
            source: Configured scrape source with decrypted credentials.

        Returns:
            List of scraped posts (may be empty if no new content).

        Raises:
            ScraperError: On non-recoverable scraping failures.
            ScraperAuthError: On authentication failures (expired cookie, etc.).
        """
        ...
