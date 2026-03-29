"""
Supabase service-role client.

Uses the service-role key for server-side operations (ingestion, admin tasks).
The service-role key bypasses RLS — never expose it to the client.

All calls from async endpoints must be wrapped in run_in_executor
(Supabase Python client is synchronous).
See conventions.md § Supabase in Async Code.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client  # type: ignore[import]

from app.core.config import settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return a cached Supabase service-role client.

    WARNING: This singleton shares one httpx connection pool. Do NOT pass it
    to background tasks that run in executor threads — use create_supabase()
    instead to avoid HTTP/2 stream contention (Errno 35 / EAGAIN).
    """
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def create_supabase() -> Client:
    """Create a fresh (non-cached) Supabase client.

    Use this for background tasks (ingestion pipeline, etc.) that run
    concurrently with request handlers. Each background task gets its own
    httpx connection pool, avoiding HTTP/2 stream contention with the
    singleton returned by get_supabase().
    """
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
