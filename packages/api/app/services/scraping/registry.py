"""
Scraper registry — KIN-461.

Maps source_type strings to scraper class instances.
Adding a new source type = add a class + registry entry.

Design doc: docs/plans/2026-04-05-scheduled-kb-scraping-design.md § Scraper Architecture.
"""

from __future__ import annotations

from app.services.scraping.base import BaseScraper
from app.services.scraping.rss import RSSFeedScraper
from app.services.scraping.substack import SubstackScraper

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "substack": SubstackScraper,
    "rss": RSSFeedScraper,
}


def get_scraper(source_type: str) -> BaseScraper:
    """Return a scraper instance for the given source type.

    Args:
        source_type: One of the keys in SCRAPER_REGISTRY (e.g., "substack", "rss").

    Returns:
        An instance of the appropriate BaseScraper subclass.

    Raises:
        ValueError: If source_type is not in the registry.
    """
    cls = SCRAPER_REGISTRY.get(source_type)
    if cls is None:
        supported = ", ".join(sorted(SCRAPER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown scraper source_type '{source_type}'. Supported: {supported}"
        )
    return cls()
