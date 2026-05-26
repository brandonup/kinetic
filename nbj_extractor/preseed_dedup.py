#!/usr/bin/env python3
"""
Pre-seed the scrape-source dedup table for the Nate B. Jones Substack source.

One-time ops script. Run ONCE, right after the `scrape_sources` row is created,
so the production poller does NOT re-ingest the ~567 articles already
bulk-loaded into the Nate B. Jones knowledge base.

What it does:
  1. Fetches every post currently published on natesnewsletter.substack.com
     (public Substack API — no credential needed).
  2. Inserts one `scrape_source_posts` dedup row per post. Idempotent — safe
     to re-run; existing rows are ignored via the unique constraint.
  3. Activates the scrape source (is_active=true, next_run_at=now) so the
     production poller starts its daily cycle on its next 5-minute tick.

After this runs, the poller only ingests posts published AFTER this point.

Usage (from the nbj_extractor directory):

    cd /Users/brandonupchuch/son_of_anton/projects/kinetic/nbj_extractor

    # Create a gitignored .env file next to this script containing:
    #   SUPABASE_SERVICE_ROLE_KEY=<prod service_role key>
    #   SCRAPE_SOURCE_ID=<id returned when the scrape source was created>

    python preseed_dedup.py --dry-run     # preview: fetch posts, no writes
    python preseed_dedup.py               # real run: insert dedup rows + activate

    # Recommended (KIN-490): pass the KB ID to skip posts not already in the KB.
    # Only dedup rows that have a matching KB doc are inserted; the rest are
    # left for the poller to ingest fresh on its next run.
    python preseed_dedup.py --knowledge-base-id 91db7050-aa0b-403a-8faf-dcdcd095add0

Requirements: `requests` (already used by substack_scraper.py / bulk_upload_to_kb.py).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# --- Constants --------------------------------------------------------------

ENV_FILE_NAME = ".env"

SUBSTACK_URL_DEFAULT = "https://natesnewsletter.substack.com"
SUPABASE_URL_DEFAULT = "https://iiapaogaoadtvjnryuls.supabase.co"  # prod
KINETIC_USER_ID_DEFAULT = "deb3cbfc-be6c-49e1-ab5c-777a9f308910"  # Brandon, prod

PAGE_SIZE = 25          # Substack API page size
REQUEST_DELAY = 0.75    # seconds between paginated Substack requests
INSERT_BATCH_SIZE = 200  # rows per PostgREST insert request
HTTP_TIMEOUT_S = 60

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko)"
)

logger = logging.getLogger("preseed_dedup")


# --- Environment ------------------------------------------------------------

def load_env_file(path: Path) -> None:
    """Merge KEY=VALUE lines from a .env file into os.environ.

    Existing environment variables take precedence (setdefault), so an
    explicit `export` always wins over the file.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# --- Substack ---------------------------------------------------------------

def fetch_all_posts(substack_url: str) -> list[dict]:
    """Fetch every post via the paginated public Substack API."""
    posts: list[dict] = []
    offset = 0
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    while True:
        resp = session.get(
            f"{substack_url.rstrip('/')}/api/v1/posts",
            params={"limit": PAGE_SIZE, "offset": offset},
            timeout=HTTP_TIMEOUT_S,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch or not isinstance(batch, list):
            break

        posts.extend(batch)
        logger.info("Fetched %d posts (offset %d)", len(posts), offset)

        if len(batch) < PAGE_SIZE:
            break  # last page
        offset += PAGE_SIZE
        time.sleep(REQUEST_DELAY)

    return posts


def extract_slug_from_url(url: str) -> Optional[str]:
    """Return the Substack post slug from a canonical URL (.../p/<slug>)."""
    if not url:
        return None
    path = url.split("?")[0].split("#")[0].rstrip("/")
    parts = path.rsplit("/p/", 1)
    if len(parts) == 2 and parts[1]:
        return parts[1]
    return None


def fetch_kb_slugs(
    supabase_url: str, service_role_key: str, knowledge_base_id: str
) -> set[str]:
    """Return the set of post slugs already present in a knowledge base.

    KB documents created by bulk_upload_to_kb.py are stored with title
    ``<slug>.txt``. Stripping the ``.txt`` suffix yields the matching slug.
    Documents with non-slug titles (e.g. full article titles) are skipped.
    """
    endpoint = (
        f"{supabase_url.rstrip('/')}/rest/v1/knowledge_base_documents"
        f"?knowledge_base_id=eq.{knowledge_base_id}&select=title"
    )
    headers = _service_headers(service_role_key)
    slugs: set[str] = set()
    offset = 0
    batch_size = 1000

    while True:
        paged_headers = {**headers, "Range": f"{offset}-{offset + batch_size - 1}"}
        resp = requests.get(endpoint, headers=paged_headers, timeout=HTTP_TIMEOUT_S)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for row in batch:
            title = (row.get("title") or "").strip()
            slug = title.removesuffix(".txt")
            # Only add slug-like titles (no spaces); skip full prose titles.
            if slug and " " not in slug:
                slugs.add(slug)
        if len(batch) < batch_size:
            break
        offset += batch_size

    return slugs


def build_dedup_rows(
    posts: list[dict],
    scrape_source_id: str,
    user_id: str,
    known_slugs: Optional[set[str]] = None,
) -> tuple[list[dict], int, int]:
    """Build scrape_source_posts rows.

    `external_id` mirrors SubstackScraper.scrape() exactly — `str(meta["id"])`
    — so the keys line up with what the production poller will dedup against.

    If `known_slugs` is provided, only posts whose URL slug appears in the set
    are included. Posts with no matching slug are counted as orphans and skipped.
    This prevents preseed from blocking future ingestion of posts that were
    never bulk-loaded into the KB (KIN-490).
    """
    rows: list[dict] = []
    skipped_no_id = 0
    orphans = 0
    for meta in posts:
        post_id = meta.get("id")
        if post_id is None:
            skipped_no_id += 1
            continue
        if known_slugs is not None:
            slug = extract_slug_from_url(meta.get("canonical_url") or "")
            if slug not in known_slugs:
                orphans += 1
                logger.debug(
                    "Orphan — slug %r not in KB, skipping post id=%s", slug, post_id
                )
                continue
        rows.append(
            {
                "scrape_source_id": scrape_source_id,
                "user_id": user_id,
                "external_id": str(post_id),
                "url": meta.get("canonical_url") or "",
                "title": (meta.get("title") or "").strip(),
            }
        )
    return rows, skipped_no_id, orphans


# --- Supabase PostgREST -----------------------------------------------------

def _service_headers(service_role_key: str) -> dict[str, str]:
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }


def insert_dedup_rows(
    supabase_url: str, service_role_key: str, rows: list[dict]
) -> None:
    """Bulk-insert dedup rows. Ignores rows that already exist (idempotent)."""
    endpoint = (
        f"{supabase_url.rstrip('/')}/rest/v1/scrape_source_posts"
        "?on_conflict=scrape_source_id,external_id"
    )
    headers = _service_headers(service_role_key)
    headers["Prefer"] = "resolution=ignore-duplicates,return=minimal"

    for i in range(0, len(rows), INSERT_BATCH_SIZE):
        batch = rows[i : i + INSERT_BATCH_SIZE]
        resp = requests.post(endpoint, headers=headers, json=batch, timeout=HTTP_TIMEOUT_S)
        if resp.status_code not in (200, 201, 204):
            raise RuntimeError(
                f"PostgREST insert failed: HTTP {resp.status_code}: {resp.text[:300]}"
            )
        logger.info("Inserted batch %d-%d", i, i + len(batch) - 1)


def count_dedup_rows(
    supabase_url: str, service_role_key: str, scrape_source_id: str
) -> Optional[int]:
    """Return the exact count of dedup rows for the source via Content-Range."""
    endpoint = (
        f"{supabase_url.rstrip('/')}/rest/v1/scrape_source_posts"
        f"?scrape_source_id=eq.{scrape_source_id}&select=id"
    )
    headers = _service_headers(service_role_key)
    headers["Prefer"] = "count=exact"
    headers["Range"] = "0-0"
    resp = requests.get(endpoint, headers=headers, timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    content_range = resp.headers.get("Content-Range", "")
    if "/" in content_range:
        total = content_range.rsplit("/", 1)[-1]
        if total.isdigit():
            return int(total)
    return None


def activate_source(
    supabase_url: str, service_role_key: str, scrape_source_id: str
) -> dict:
    """Set is_active=true and next_run_at=now so the poller picks it up soon."""
    endpoint = (
        f"{supabase_url.rstrip('/')}/rest/v1/scrape_sources?id=eq.{scrape_source_id}"
    )
    headers = _service_headers(service_role_key)
    headers["Prefer"] = "return=representation"
    body = {
        "is_active": True,
        "next_run_at": datetime.now(timezone.utc).isoformat(),
        "consecutive_failures": 0,
        "last_error": None,
    }
    resp = requests.patch(endpoint, headers=headers, json=body, timeout=HTTP_TIMEOUT_S)
    if resp.status_code not in (200, 204):
        raise RuntimeError(
            f"Failed to activate source: HTTP {resp.status_code}: {resp.text[:300]}"
        )
    data = resp.json()
    if not data:
        raise RuntimeError(
            f"Source {scrape_source_id} not found — check SCRAPE_SOURCE_ID."
        )
    return data[0]


# --- CLI --------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-seed the scrape-source dedup table for the Nate Substack source.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch posts and report counts, but make no database writes.",
    )
    parser.add_argument(
        "--substack-url",
        default=SUBSTACK_URL_DEFAULT,
        help=f"Substack base URL (default: {SUBSTACK_URL_DEFAULT}).",
    )
    parser.add_argument(
        "--supabase-url",
        default=SUPABASE_URL_DEFAULT,
        help=f"Supabase project URL (default: prod, {SUPABASE_URL_DEFAULT}).",
    )
    parser.add_argument(
        "--user-id",
        default=KINETIC_USER_ID_DEFAULT,
        help="Owning Kinetic user UUID (default: Brandon's prod user).",
    )
    parser.add_argument(
        "--knowledge-base-id",
        default=None,
        help=(
            "UUID of the target knowledge base. When provided, only posts whose URL "
            "slug matches a document already in the KB are seeded. Posts with no "
            "matching KB doc are skipped (orphan prevention — KIN-490)."
        ),
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging.")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    script_dir = Path(__file__).resolve().parent
    load_env_file(script_dir / ENV_FILE_NAME)

    scrape_source_id = os.environ.get("SCRAPE_SOURCE_ID", "").strip()
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not scrape_source_id:
        logger.error("Missing SCRAPE_SOURCE_ID (set it in .env or the environment).")
        return 2
    needs_key = not args.dry_run or bool(args.knowledge_base_id)
    if needs_key and not service_role_key:
        logger.error(
            "Missing SUPABASE_SERVICE_ROLE_KEY (set it in .env or the environment)."
        )
        return 2

    # --- KB slug filter (KIN-490) ------------------------------------------
    known_slugs: Optional[set[str]] = None
    if args.knowledge_base_id:
        logger.info(
            "Fetching KB slugs for knowledge_base_id=%s ...", args.knowledge_base_id
        )
        known_slugs = fetch_kb_slugs(
            args.supabase_url, service_role_key, args.knowledge_base_id
        )
        logger.info("KB contains %d slug(s) to match against.", len(known_slugs))

    # --- Fetch -------------------------------------------------------------
    logger.info("Fetching all posts from %s ...", args.substack_url)
    posts = fetch_all_posts(args.substack_url)
    rows, skipped_no_id, orphans = build_dedup_rows(
        posts, scrape_source_id, args.user_id, known_slugs=known_slugs
    )
    logger.info(
        "Fetched %d posts — %d dedup rows to seed, %d skipped (no id), %d orphans skipped.",
        len(posts), len(rows), skipped_no_id, orphans,
    )

    if not rows:
        logger.error("No posts with an id were found — aborting.")
        return 1

    if args.dry_run:
        print()
        print("=== Pre-seed dry run ===")
        print(f"Substack:        {args.substack_url}")
        print(f"Scrape source:   {scrape_source_id}")
        print(f"KB filter:       {'enabled (KB=' + args.knowledge_base_id + ')' if args.knowledge_base_id else 'disabled'}")
        print(f"Posts fetched:   {len(posts)}")
        print(f"Dedup rows:      {len(rows)} would be inserted (ignore-on-conflict)")
        print(f"Skipped (no id): {skipped_no_id}")
        print(f"Orphans skipped: {orphans}")
        print("First 3 rows:")
        for row in rows[:3]:
            print(f"  - external_id={row['external_id']}  {row['title'][:70]!r}")
        print("\nNo writes performed. Re-run without --dry-run to apply.")
        return 0

    # --- Insert ------------------------------------------------------------
    logger.info("Inserting %d dedup rows ...", len(rows))
    insert_dedup_rows(args.supabase_url, service_role_key, rows)

    total = count_dedup_rows(args.supabase_url, service_role_key, scrape_source_id)
    logger.info("Dedup table now holds %s row(s) for this source.", total)

    # --- Activate ----------------------------------------------------------
    logger.info("Activating scrape source ...")
    source = activate_source(args.supabase_url, service_role_key, scrape_source_id)

    print()
    print("=== Pre-seed complete ===")
    print(f"Scrape source:   {scrape_source_id}")
    print(f"KB filter:       {'enabled (KB=' + args.knowledge_base_id + ')' if args.knowledge_base_id else 'disabled'}")
    print(f"Posts fetched:   {len(posts)}")
    print(f"Orphans skipped: {orphans}")
    print(f"Dedup rows seeded: {total}")
    print(f"is_active:       {source.get('is_active')}")
    print(f"next_run_at:     {source.get('next_run_at')}")
    print()
    print("The production poller will run within ~5 minutes. Its first run should")
    print("report 0 new posts (everything currently published is now de-duped).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
