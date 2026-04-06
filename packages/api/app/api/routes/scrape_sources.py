"""
Scrape sources CRUD + manual run — KIN-463.

Backend-only API for managing scheduled KB scraping sources.
UI comes later. All unauthorized access returns 404 (not 403)
to prevent UUID enumeration.

Design doc: docs/plans/2026-04-05-scheduled-kb-scraping-design.md § API Endpoints
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scrape-sources"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

VALID_SOURCE_TYPES = {"substack", "rss"}
VALID_FREQUENCIES = {"daily", "weekly", "monthly"}
FREQUENCY_DELTAS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}

# Response columns — NEVER includes credential_ciphertext or credential_nonce
SAFE_COLUMNS = (
    "id, knowledge_base_id, user_id, source_type, source_url, frequency, "
    "is_active, last_scraped_at, next_run_at, last_error, "
    "consecutive_failures, created_at, updated_at"
)


class CreateScrapeSourceRequest(BaseModel):
    knowledge_base_id: str
    source_type: str
    source_url: str
    frequency: str
    credential: Optional[str] = None  # Plaintext cookie/token, encrypted before storage

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        if v not in VALID_SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {VALID_SOURCE_TYPES}")
        return v

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        if v not in VALID_FREQUENCIES:
            raise ValueError(f"frequency must be one of {VALID_FREQUENCIES}")
        return v

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        parsed = urlparse(v.strip())
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("source_url must be a valid URL with scheme and host")
        return v.strip()


class UpdateScrapeSourceRequest(BaseModel):
    frequency: Optional[str] = None
    is_active: Optional[bool] = None
    credential: Optional[str] = None  # Re-encrypt on update

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_FREQUENCIES:
            raise ValueError(f"frequency must be one of {VALID_FREQUENCIES}")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client():
    """Return the service-role Supabase client."""
    return get_supabase()


async def _verify_kb_ownership(client, kb_id: str, user_id: str) -> None:
    """Verify the user owns the knowledge base. Raises 404 if not."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client.table("knowledge_bases")
        .select("id")
        .eq("id", kb_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute(),
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Knowledge base not found")


async def _verify_byok_key(client, user_id: str) -> None:
    """Verify user has an OpenAI BYOK key. Raises 400 if not.

    MVP: hardcoded to OpenAI. Future: support multi-provider per source type.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client.table("user_api_keys")
        .select("id")
        .eq("user_id", user_id)
        .eq("provider", "openai")
        .maybe_single()
        .execute(),
    )
    if not result.data:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API key required. Add one in Settings before configuring a scrape source.",
        )


def _encrypt_credential(plaintext: str, user_id: str) -> tuple[str, str]:
    """Encrypt a credential and return (ciphertext_hex, nonce_hex) for DB storage."""
    from app.services.encryption import encrypt_api_key, load_master_key

    master_key = load_master_key()
    ciphertext, nonce = encrypt_api_key(plaintext, master_key, user_id)
    # Store as hex strings for Supabase bytea columns
    return ciphertext.hex(), nonce.hex()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/v1/scrape-sources", status_code=status.HTTP_201_CREATED)
async def create_scrape_source(
    body: CreateScrapeSourceRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Create a new scrape source for a knowledge base."""
    loop = asyncio.get_running_loop()
    client = _get_client()
    user_id = current_user.user_id

    # Validate ownership and BYOK key
    await _verify_kb_ownership(client, body.knowledge_base_id, user_id)
    await _verify_byok_key(client, user_id)

    # Build insert row
    now = datetime.now(timezone.utc)
    next_run_at = now + FREQUENCY_DELTAS[body.frequency]

    row: dict = {
        "knowledge_base_id": body.knowledge_base_id,
        "user_id": user_id,
        "source_type": body.source_type,
        "source_url": body.source_url,
        "frequency": body.frequency,
        "next_run_at": next_run_at.isoformat(),
    }

    # Encrypt credential if provided
    if body.credential:
        ct_hex, nonce_hex = _encrypt_credential(body.credential, user_id)
        row["credential_ciphertext"] = f"\\x{ct_hex}"
        row["credential_nonce"] = f"\\x{nonce_hex}"

    result = await loop.run_in_executor(
        None,
        lambda: client.table("scrape_sources")
        .insert(row)
        .execute(),
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create scrape source")

    # Re-fetch with safe columns (exclude credential fields)
    created_id = result.data[0]["id"]
    safe_result = await loop.run_in_executor(
        None,
        lambda: client.table("scrape_sources")
        .select(SAFE_COLUMNS)
        .eq("id", created_id)
        .single()
        .execute(),
    )
    return safe_result.data


@router.get("/api/v1/scrape-sources")
async def list_scrape_sources(
    knowledge_base_id: str = Query(..., description="Filter by knowledge base ID"),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """List scrape sources for a knowledge base. RLS filters to user's own."""
    loop = asyncio.get_running_loop()
    client = _get_client()

    result = await loop.run_in_executor(
        None,
        lambda: client.table("scrape_sources")
        .select(SAFE_COLUMNS)
        .eq("knowledge_base_id", knowledge_base_id)
        .eq("user_id", current_user.user_id)
        .order("created_at", desc=True)
        .execute(),
    )
    return result.data or []


@router.patch("/api/v1/scrape-sources/{source_id}")
async def update_scrape_source(
    source_id: str,
    body: UpdateScrapeSourceRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Update a scrape source. Ownership check returns 404 if not owner."""
    loop = asyncio.get_running_loop()
    client = _get_client()
    user_id = current_user.user_id

    # Ownership check
    existing = await loop.run_in_executor(
        None,
        lambda: client.table("scrape_sources")
        .select("id, frequency, is_active")
        .eq("id", source_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute(),
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Scrape source not found")

    # Build update payload
    updates: dict = {}

    if body.frequency is not None:
        updates["frequency"] = body.frequency
        # Recalculate next_run_at when frequency changes
        now = datetime.now(timezone.utc)
        updates["next_run_at"] = (now + FREQUENCY_DELTAS[body.frequency]).isoformat()

    if body.is_active is not None:
        updates["is_active"] = body.is_active
        # Re-activating: reset failure counter and recalculate next_run_at
        if body.is_active and not existing.data.get("is_active"):
            updates["consecutive_failures"] = 0
            updates["last_error"] = None
            freq = body.frequency or existing.data["frequency"]
            now = datetime.now(timezone.utc)
            updates["next_run_at"] = (now + FREQUENCY_DELTAS[freq]).isoformat()

    if body.credential is not None:
        ct_hex, nonce_hex = _encrypt_credential(body.credential, user_id)
        updates["credential_ciphertext"] = f"\\x{ct_hex}"
        updates["credential_nonce"] = f"\\x{nonce_hex}"

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await loop.run_in_executor(
        None,
        lambda: client.table("scrape_sources")
        .update(updates)
        .eq("id", source_id)
        .eq("user_id", user_id)
        .execute(),
    )

    # Re-fetch with safe columns
    safe_result = await loop.run_in_executor(
        None,
        lambda: client.table("scrape_sources")
        .select(SAFE_COLUMNS)
        .eq("id", source_id)
        .single()
        .execute(),
    )
    return safe_result.data


@router.delete(
    "/api/v1/scrape-sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_scrape_source(
    source_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a scrape source. CASCADE deletes scrape_source_posts."""
    loop = asyncio.get_running_loop()
    client = _get_client()
    user_id = current_user.user_id

    # Ownership check
    existing = await loop.run_in_executor(
        None,
        lambda: client.table("scrape_sources")
        .select("id")
        .eq("id", source_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute(),
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Scrape source not found")

    await loop.run_in_executor(
        None,
        lambda: client.table("scrape_sources")
        .delete()
        .eq("id", source_id)
        .execute(),
    )


@router.post("/api/v1/scrape-sources/{source_id}/run")
async def run_scrape_source(
    source_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Trigger an immediate scrape (bypasses next_run_at scheduling).

    Returns a summary of results: posts_found, posts_new, posts_skipped.
    """
    loop = asyncio.get_running_loop()
    client = _get_client()
    user_id = current_user.user_id

    # Fetch source with credential fields for decryption
    source_row = await loop.run_in_executor(
        None,
        lambda: client.table("scrape_sources")
        .select("*")
        .eq("id", source_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute(),
    )
    if not source_row.data:
        raise HTTPException(status_code=404, detail="Scrape source not found")

    row = source_row.data

    # Decrypt credential if present
    credential: str | None = None
    if row.get("credential_ciphertext") and row.get("credential_nonce"):
        from app.services.encryption import decrypt_api_key, load_master_key
        from app.services.user_keys import to_bytes

        try:
            master_key = load_master_key()
            ct = to_bytes(row["credential_ciphertext"])
            nonce = to_bytes(row["credential_nonce"])
            credential = decrypt_api_key(ct, nonce, master_key, user_id)
        except Exception:
            logger.error("Failed to decrypt credential for source %s", source_id, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to decrypt source credentials")

    # Build ScrapeSource model
    from app.services.scraping.base import ScrapeSource

    source = ScrapeSource(
        id=row["id"],
        knowledge_base_id=row["knowledge_base_id"],
        user_id=user_id,
        source_type=row["source_type"],
        source_url=row["source_url"],
        frequency=row["frequency"],
        credential=credential,
        is_active=row["is_active"],
        last_scraped_at=row.get("last_scraped_at"),
        next_run_at=row["next_run_at"],
        consecutive_failures=row.get("consecutive_failures", 0),
    )

    # Get the scraper and run
    from app.services.scraping.registry import get_scraper

    scraper = get_scraper(source.source_type)

    try:
        posts = await scraper.scrape(source)
    except Exception as exc:
        # Update failure state
        failures = row.get("consecutive_failures", 0) + 1
        update_data: dict = {
            "consecutive_failures": failures,
            "last_error": str(exc)[:500],
        }
        if failures >= 5:
            update_data["is_active"] = False
        await loop.run_in_executor(
            None,
            lambda: client.table("scrape_sources")
            .update(update_data)
            .eq("id", source_id)
            .execute(),
        )
        raise HTTPException(
            status_code=502,
            detail=f"Scrape failed: {str(exc)[:200]}",
        )

    # Deduplicate against existing posts
    existing_result = await loop.run_in_executor(
        None,
        lambda: client.table("scrape_source_posts")
        .select("external_id")
        .eq("scrape_source_id", source_id)
        .execute(),
    )
    existing_ids = {r["external_id"] for r in (existing_result.data or [])}

    new_posts = [p for p in posts if p.external_id not in existing_ids]

    # Insert new posts
    for post in new_posts:
        await loop.run_in_executor(
            None,
            lambda post=post: client.table("scrape_source_posts")
            .insert({
                "scrape_source_id": source_id,
                "user_id": user_id,
                "external_id": post.external_id,
                "url": post.url,
                "title": post.title,
            })
            .execute(),
        )

    # Update source success state
    now = datetime.now(timezone.utc)
    next_run = now + FREQUENCY_DELTAS[row["frequency"]]
    await loop.run_in_executor(
        None,
        lambda: client.table("scrape_sources")
        .update({
            "last_scraped_at": now.isoformat(),
            "next_run_at": next_run.isoformat(),
            "consecutive_failures": 0,
            "last_error": None,
        })
        .eq("id", source_id)
        .execute(),
    )

    return {
        "posts_found": len(posts),
        "posts_new": len(new_posts),
        "posts_skipped": len(posts) - len(new_posts),
    }
