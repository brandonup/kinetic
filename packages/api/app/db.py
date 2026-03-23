"""
Supabase client singleton — Kinetic API.

Uses the service role key so backend can bypass RLS for trusted operations.
Application code must enforce ownership checks at the API layer.
"""

from __future__ import annotations

import os
from typing import Any

_client: Any = None


def get_supabase_client() -> Any:
    """Return the shared Supabase client, initialising it on first call."""
    global _client
    if _client is None:
        try:
            from supabase import create_client
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("supabase package not installed") from exc

        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:  # pragma: no cover
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"
            )
        _client = create_client(url, key)
    return _client


def reset_client() -> None:
    """Reset the singleton — used in tests to swap in a mock."""
    global _client
    _client = None
