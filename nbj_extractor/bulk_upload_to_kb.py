#!/usr/bin/env python3
"""
Bulk-upload Nate's article corpus to a Kinetic Knowledge Base.

One-off ops script. Posts each JSON in ``articles/`` as a separate document
to ``POST /api/v1/documents/upload`` so each chunk citation names the
specific article/episode (via the ``Source: {title}`` header from KIN-468).

Usage (from the nbj_extractor directory):

    cd /Users/brandonupchuch/son_of_anton/projects/kinetic/nbj_extractor
    export KINETIC_USER_JWT='<paste JWT from the web app session>'

    # Dry run first — preview the payload for a few files:
    python bulk_upload_to_kb.py \\
        --kb <nate-kb-uuid> \\
        --base-url https://kinetic-production-b568.up.railway.app \\
        --limit 3 --dry-run

    # Real run with resume + ingestion wait:
    python bulk_upload_to_kb.py \\
        --kb <nate-kb-uuid> \\
        --base-url https://kinetic-production-b568.up.railway.app \\
        --resume --wait-for-ingestion

Requirements: ``requests`` (same library used by ``substack_scraper.py``).

Per the ticket (KIN-475): DO NOT run on the prod KB until the KIN-471
smoke test passes on transcript chunking quality with
``SEMANTIC_CHUNKING_ENABLED=True``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# --- Constants --------------------------------------------------------------

ARTICLES_DIR_NAME = "articles"
PROGRESS_FILE_NAME = "bulk_upload_progress.jsonl"
ENV_JWT = "KINETIC_USER_JWT"

SLEEP_BETWEEN_REQUESTS_S = 0.25
RATE_LIMIT_BACKOFF_S = [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]  # capped at 30s
MAX_CONSECUTIVE_FAILURES_PER_FILE = 3
TRANSIENT_RETRY_SLEEP_S = 1.0

UPLOAD_TIMEOUT_S = 120
POLL_TIMEOUT_S = 30
POLL_INTERVAL_S = 5.0
INGESTION_DEADLINE_S = 30 * 60  # 30 minutes per document
TERMINAL_STATUSES = ("completed", "failed")

logger = logging.getLogger("bulk_upload")


# --- IO helpers -------------------------------------------------------------

def load_progress(progress_path: Path) -> dict[str, str]:
    """Return {slug: latest_status} from the progress file.

    Later lines for the same slug override earlier lines, so the file is
    safe to append to across multiple runs.
    """
    if not progress_path.exists():
        return {}
    statuses: dict[str, str] = {}
    with progress_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed progress line %d", line_num)
                continue
            slug = row.get("slug")
            status = row.get("status")
            if slug and status:
                statuses[slug] = status
    return statuses


def append_progress(
    progress_path: Path,
    slug: str,
    document_id: Optional[str],
    status: str,
    error: Optional[str],
) -> None:
    """Atomically append a single line to the progress file."""
    row = {
        "slug": slug,
        "document_id": document_id,
        "status": status,
        "error": error,
        "attempted_at": datetime.now(timezone.utc).isoformat(),
    }
    # Open-append-close per write so an interrupted run still leaves a valid file.
    with progress_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


# --- Payload conversion -----------------------------------------------------

def convert_article(article: dict) -> str:
    """Build the plain-text payload body documented in the ticket."""
    return (
        f"Title: {article.get('title', '')}\n"
        f"Subtitle: {article.get('subtitle', '')}\n"
        f"URL: {article.get('url', '')}\n"
        f"Date: {article.get('date', '')}\n"
        f"Type: {article.get('type', '')}\n"
        f"\n"
        f"{article.get('content', '')}"
    )


def iter_articles(articles_dir: Path):
    """Yield (slug, article_dict, source_path) sorted by filename for deterministic order."""
    for path in sorted(articles_dir.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read %s: %s", path.name, exc)
            continue
        slug = data.get("slug") or path.stem
        yield slug, data, path


# --- HTTP -------------------------------------------------------------------

class UploadError(Exception):
    """Permanent upload failure for a single file."""


def _post_upload_once(
    session: requests.Session,
    base_url: str,
    kb_id: str,
    filename: str,
    body: str,
) -> requests.Response:
    return session.post(
        f"{base_url.rstrip('/')}/api/v1/documents/upload",
        files={"file": (filename, body.encode("utf-8"), "text/plain")},
        data={"knowledge_base_id": kb_id},
        timeout=UPLOAD_TIMEOUT_S,
    )


def upload_with_retry(
    session: requests.Session,
    base_url: str,
    kb_id: str,
    filename: str,
    body: str,
) -> str:
    """POST a single file with up to MAX_CONSECUTIVE_FAILURES_PER_FILE attempts.

    429s use the documented exponential backoff schedule. Other transient
    errors (network, 5xx) sleep TRANSIENT_RETRY_SLEEP_S between attempts.
    4xx non-429 responses are treated as permanent for this file.

    Returns the new document_id. Raises UploadError on permanent failure.
    """
    rate_limit_idx = 0
    last_error: Optional[str] = None

    for attempt in range(1, MAX_CONSECUTIVE_FAILURES_PER_FILE + 1):
        try:
            resp = _post_upload_once(session, base_url, kb_id, filename, body)
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
            logger.warning(
                "[%s] %s (attempt %d/%d)",
                filename, last_error, attempt, MAX_CONSECUTIVE_FAILURES_PER_FILE,
            )
            if attempt < MAX_CONSECUTIVE_FAILURES_PER_FILE:
                time.sleep(TRANSIENT_RETRY_SLEEP_S)
            continue

        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                raise UploadError(f"200 response but body was not JSON: {resp.text[:200]!r}")
            document_id = data.get("document_id")
            if not document_id:
                raise UploadError(f"200 response missing document_id: {resp.text[:200]!r}")
            return document_id

        if resp.status_code == 429:
            backoff = RATE_LIMIT_BACKOFF_S[min(rate_limit_idx, len(RATE_LIMIT_BACKOFF_S) - 1)]
            rate_limit_idx += 1
            last_error = "HTTP 429 (rate limited)"
            logger.warning("[%s] rate limited, sleeping %.1fs", filename, backoff)
            time.sleep(backoff)
            continue

        if 500 <= resp.status_code < 600:
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning(
                "[%s] %s (attempt %d/%d)",
                filename, last_error, attempt, MAX_CONSECUTIVE_FAILURES_PER_FILE,
            )
            if attempt < MAX_CONSECUTIVE_FAILURES_PER_FILE:
                time.sleep(TRANSIENT_RETRY_SLEEP_S)
            continue

        # 4xx other than 429 — permanent for this file
        raise UploadError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    raise UploadError(last_error or "exhausted retries")


def fetch_document_status(
    session: requests.Session,
    base_url: str,
    document_id: str,
) -> dict:
    """GET /api/v1/documents/{id}. Raises requests.HTTPError on non-2xx."""
    resp = session.get(
        f"{base_url.rstrip('/')}/api/v1/documents/{document_id}",
        timeout=POLL_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()


def poll_until_terminal(
    session: requests.Session,
    base_url: str,
    document_id: str,
    deadline_s: float,
) -> tuple[str, Optional[str]]:
    """Poll the document status endpoint until it reaches a terminal state.

    Returns (final_status, error_message). On timeout, status = 'timeout'.
    """
    start = time.monotonic()
    while True:
        try:
            doc = fetch_document_status(session, base_url, document_id)
        except requests.RequestException as exc:
            logger.warning("[%s] status poll failed: %s — retrying", document_id, exc)
            time.sleep(POLL_INTERVAL_S)
            if time.monotonic() - start > deadline_s:
                return "timeout", f"poll error: {exc}"
            continue

        status = doc.get("status", "unknown")
        if status in TERMINAL_STATUSES:
            return status, doc.get("error_message")
        if time.monotonic() - start > deadline_s:
            return "timeout", f"still {status} after {deadline_s:.0f}s"
        time.sleep(POLL_INTERVAL_S)


# --- CLI --------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-upload Nate's article corpus to a Kinetic Knowledge Base.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--kb", required=True, help="Target knowledge_base_id (UUID).")
    parser.add_argument(
        "--base-url",
        required=True,
        help="API base URL, e.g. https://kinetic-production-b568.up.railway.app",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only attempt the first N articles.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be uploaded, no API calls.")
    parser.add_argument("--resume", action="store_true", help="Skip slugs marked 'succeeded' in the progress file.")
    parser.add_argument(
        "--wait-for-ingestion",
        action="store_true",
        help="After all uploads, poll each document until ingestion completes or fails.",
    )
    parser.add_argument(
        "--articles-dir",
        type=Path,
        default=None,
        help="Override the articles directory (defaults to ./articles next to this script).",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")
    return parser.parse_args(argv)


def make_session(jwt: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {jwt}"})
    return session


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    script_dir = Path(__file__).resolve().parent
    articles_dir = (args.articles_dir or script_dir / ARTICLES_DIR_NAME).resolve()
    progress_path = script_dir / PROGRESS_FILE_NAME

    if not articles_dir.is_dir():
        logger.error("Articles directory not found: %s", articles_dir)
        return 2

    # JWT only required for real runs.
    jwt = os.environ.get(ENV_JWT, "")
    if not args.dry_run and not jwt:
        logger.error(
            "Missing %s env var. Copy your JWT from the web app session and export it before running.",
            ENV_JWT,
        )
        return 2

    prior = load_progress(progress_path) if args.resume else {}
    if args.resume:
        already_done = sum(1 for v in prior.values() if v == "succeeded")
        logger.info("Resume mode: %d slugs marked 'succeeded' will be skipped.", already_done)

    session: Optional[requests.Session] = None
    if not args.dry_run:
        session = make_session(jwt)

    succeeded: list[tuple[str, str]] = []  # (slug, document_id)
    skipped: list[str] = []
    failed: list[tuple[str, str]] = []  # (slug, error)
    attempts = 0

    for slug, article, path in iter_articles(articles_dir):
        if args.limit is not None and attempts >= args.limit:
            break

        if args.resume and prior.get(slug) == "succeeded":
            logger.debug("[%s] already succeeded — skipping", slug)
            skipped.append(slug)
            continue

        attempts += 1
        filename = f"{slug}.txt"
        body = convert_article(article)

        if args.dry_run:
            preview = body[:200].replace("\n", " | ")
            logger.info(
                "[dry-run] would upload %s (%d bytes) — preview: %s%s",
                filename,
                len(body.encode("utf-8")),
                preview,
                "..." if len(body) > 200 else "",
            )
            continue

        logger.info("[%d] uploading %s (%d bytes)", attempts, filename, len(body.encode("utf-8")))
        try:
            assert session is not None
            document_id = upload_with_retry(session, args.base_url, args.kb, filename, body)
        except UploadError as exc:
            err = str(exc)
            logger.error("[%s] FAILED: %s", slug, err)
            append_progress(progress_path, slug, None, "failed", err)
            failed.append((slug, err))
        else:
            logger.info("[%s] uploaded -> %s", slug, document_id)
            append_progress(progress_path, slug, document_id, "succeeded", None)
            succeeded.append((slug, document_id))

        # Rate-friendly pacing between sequential POSTs.
        time.sleep(SLEEP_BETWEEN_REQUESTS_S)

    # --- Ingestion poll (optional) -----------------------------------------
    ingestion_outcomes: dict[str, tuple[str, Optional[str]]] = {}
    if args.wait_for_ingestion and not args.dry_run and succeeded:
        logger.info(
            "Polling ingestion status for %d documents (deadline %.0fs each)…",
            len(succeeded), INGESTION_DEADLINE_S,
        )
        assert session is not None
        for slug, document_id in succeeded:
            status, err = poll_until_terminal(session, args.base_url, document_id, INGESTION_DEADLINE_S)
            ingestion_outcomes[slug] = (status, err)
            logger.info("[%s] ingestion=%s%s", slug, status, f" ({err})" if err else "")

    # --- Final report -------------------------------------------------------
    print()
    print("=== Bulk upload report ===")
    print(f"Articles directory: {articles_dir}")
    print(f"Progress file:      {progress_path}")
    if args.dry_run:
        print(f"Dry-run: {attempts} files would be uploaded.")
        return 0

    print(f"Succeeded (uploaded): {len(succeeded)}")
    print(f"Skipped (resume):     {len(skipped)}")
    print(f"Failed:               {len(failed)}")
    if failed:
        print("\nFailed details:")
        for slug, err in failed:
            print(f"  - {slug}: {err}")

    ingestion_failed: list[tuple[str, str, Optional[str]]] = []
    if args.wait_for_ingestion:
        completed = sum(1 for s, _ in ingestion_outcomes.values() if s == "completed")
        ingest_failed_count = sum(1 for s, _ in ingestion_outcomes.values() if s == "failed")
        timed_out = sum(1 for s, _ in ingestion_outcomes.values() if s == "timeout")
        print()
        print(f"Ingestion completed: {completed}")
        print(f"Ingestion failed:    {ingest_failed_count}")
        print(f"Ingestion timeout:   {timed_out}")
        for slug, (status, err) in ingestion_outcomes.items():
            if status != "completed":
                ingestion_failed.append((slug, status, err))
        if ingestion_failed:
            print("\nIngestion failures:")
            for slug, status, err in ingestion_failed:
                print(f"  - {slug}: {status}{f' ({err})' if err else ''}")

    has_failures = bool(failed) or bool(ingestion_failed)
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
