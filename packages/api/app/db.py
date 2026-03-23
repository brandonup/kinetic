"""
Supabase client factory.

get_supabase_client() returns a module-level singleton. Tests patch
`app.db._supabase_client` directly to inject a mock.
"""
from __future__ import annotations

from typing import Any

from app.config import get_settings

# Module-level client — None until first call (or test injection)
_supabase_client: Any = None


def get_supabase_client() -> Any:
    """Return the Supabase client singleton, creating it on first call."""
    global _supabase_client
    if _supabase_client is None:
        settings = get_settings()
        try:
            from supabase import create_client  # type: ignore[import]

            _supabase_client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialise Supabase client: {exc}"
            ) from exc
    return _supabase_client
