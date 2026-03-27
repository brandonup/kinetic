"""
Shared BYOK key fetch + decrypt helpers.

Consolidates the user_api_keys fetch/decrypt pattern used across routes
(conversations, linked_upload, agents, documents, MCP).

Schema ref: docs/db-schema-spec.md §2 (user_api_keys)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.services.encryption import decrypt_api_key, load_master_key

logger = logging.getLogger(__name__)


def to_bytes(val) -> bytes:
    """
    Convert a Supabase bytea field value to bytes.

    Supabase/PostgREST may return bytea columns as:
    - raw bytes (bytes/bytearray) — pass through
    - '\\x{hex}' prefixed hex string — strip prefix and decode
    - plain hex string (as stored by profile routes via .hex()) — decode directly
    """
    if isinstance(val, (bytes, bytearray)):
        return bytes(val)
    s = str(val)
    if s.startswith("\\x"):
        s = s[2:]
    return bytes.fromhex(s)


def fetch_user_key(supabase, user_id: str, provider: str) -> Optional[str]:
    """
    Fetch and decrypt a user's API key by provider.

    Args:
        supabase: Supabase service-role client (sync).
        user_id: User UUID string.
        provider: Key provider — "openai", "anthropic", "google", or "groq".

    Returns:
        Decrypted plaintext API key, or None if the user has no key for this provider.
    """
    result = (
        supabase.table("user_api_keys")
        .select("key_ciphertext, key_nonce")
        .eq("user_id", user_id)
        .eq("provider", provider)
        .maybe_single()
        .execute()
    )
    if not result.data:
        logger.warning(
            "fetch_user_key: no %s key row found for user %s", provider, user_id
        )
        return None

    try:
        master_key = load_master_key()
        ciphertext = to_bytes(result.data["key_ciphertext"])
        nonce = to_bytes(result.data["key_nonce"])
        return decrypt_api_key(ciphertext, nonce, master_key, user_id)
    except Exception:
        logger.error(
            "fetch_user_key: failed to decrypt %s key for user %s",
            provider,
            user_id,
            exc_info=True,
        )
        return None


async def fetch_user_key_async(
    supabase, user_id: str, provider: str,
) -> Optional[str]:
    """Async wrapper — runs fetch_user_key in executor (Supabase client is sync)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: fetch_user_key(supabase, user_id, provider),
    )
