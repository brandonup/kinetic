"""
Backfill file_size_bytes, token_count, and storage_uri for scraped KB documents.

Targets rows in knowledge_base_documents where these fields are NULL and
the document's extracted text exists in Supabase Storage at the canonical
path `{document_id}/extracted.txt`.

These rows were created by the scraper before the write-path gaps were fixed.
Manually-uploaded docs already have all fields populated.

Usage:
    cd packages/api

    # Dry run — prints what would be updated, no writes
    .venv/bin/python -m scripts.backfill_scraped_doc_fields --dry-run

    # Apply to prod
    .venv/bin/python -m scripts.backfill_scraped_doc_fields

Environment variables (same as the API server):
    SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY

Token counting uses the Gemini count_tokens API (low-frequency, non-generation).
"""

from __future__ import annotations

import argparse
import os
import sys

# ---------------------------------------------------------------------------
# Arg parsing first — before any app imports that might fail
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Backfill scraped KB document fields")
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Print what would be updated without writing anything",
)
parser.add_argument(
    "--limit",
    type=int,
    default=0,
    help="Maximum number of rows to process (0 = all)",
)
args = parser.parse_args()

# ---------------------------------------------------------------------------
# App imports (requires SUPABASE_URL / SUPABASE_KEY in env or .env)
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional

from app.db.supabase_client import get_supabase
from app.core.config import settings
from app.services.ingestion.embedder import EmbeddingService

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    supabase = get_supabase()
    embedder = EmbeddingService()

    dry_run = args.dry_run
    limit = args.limit or None

    if dry_run:
        print("[DRY RUN] No changes will be written.\n")

    # Fetch scraped docs with any NULL field we care about.
    # Restrict to docs that have no storage_uri OR no file_size_bytes OR no
    # token_count — these are the fields the scraper omitted.
    query = (
        supabase.table("knowledge_base_documents")
        .select("id, storage_uri, file_size_bytes, token_count, status")
        .is_("deleted_at", "null")
        .eq("file_type", "text/plain")
    )
    if limit:
        query = query.limit(limit)

    result = query.execute()
    rows = result.data or []

    # Filter to rows that are actually missing at least one field
    candidates = [
        r for r in rows
        if r.get("storage_uri") is None
        or r.get("file_size_bytes") is None
        or r.get("token_count") is None
    ]

    print(f"Found {len(rows)} text/plain docs total, {len(candidates)} with at least one NULL field.\n")

    updated = 0
    skipped_no_storage = 0
    failed = 0

    for row in candidates:
        doc_id = row["id"]
        storage_path = f"{doc_id}/extracted.txt"

        # Attempt to download extracted text from storage
        try:
            content: bytes = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download(storage_path)
        except Exception as exc:
            print(f"  SKIP {doc_id}: storage download failed ({exc})")
            skipped_no_storage += 1
            continue

        text = content.decode("utf-8", errors="replace")
        file_size_bytes = len(content)

        # Count tokens via Gemini (same method as new scrapes)
        try:
            token_count = embedder.count_tokens(text)
        except Exception as exc:
            print(f"  SKIP {doc_id}: token count failed ({exc})")
            failed += 1
            continue

        updates: dict = {}
        if row.get("storage_uri") is None:
            updates["storage_uri"] = storage_path
        if row.get("file_size_bytes") is None:
            updates["file_size_bytes"] = file_size_bytes
        if row.get("token_count") is None:
            updates["token_count"] = token_count

        print(
            f"  {'[DRY RUN] WOULD UPDATE' if dry_run else 'UPDATE'} {doc_id}: "
            f"file_size_bytes={file_size_bytes}, token_count={token_count}, "
            f"storage_uri={'set' if 'storage_uri' in updates else 'already set'}"
        )

        if not dry_run:
            try:
                supabase.table("knowledge_base_documents").update(updates).eq("id", doc_id).execute()
                updated += 1
            except Exception as exc:
                print(f"    ERROR writing {doc_id}: {exc}")
                failed += 1
        else:
            updated += 1

    print(
        f"\nDone. {'Would update' if dry_run else 'Updated'}: {updated}, "
        f"skipped (no storage object): {skipped_no_storage}, "
        f"errors: {failed}."
    )


if __name__ == "__main__":
    main()
