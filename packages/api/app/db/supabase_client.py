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
    """Return a cached Supabase service-role client."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
