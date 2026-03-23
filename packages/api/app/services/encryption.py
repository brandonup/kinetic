"""
AES-256-GCM encryption/decryption for BYOK API keys.

Schema ref: docs/db-schema-spec.md §2 (user_api_keys — key_ciphertext, key_nonce)
Keys are stored as base64-encoded strings in Supabase (bytea columns via REST).
The encryption key is sourced from env var API_KEY_ENCRYPTION_KEY (base64-encoded 32 bytes).
"""

from __future__ import annotations

import base64
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    pass


def _load_key() -> bytes:
    raw = os.environ.get("API_KEY_ENCRYPTION_KEY", "")
    if not raw:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY is not set")
    return base64.b64decode(raw)


def _aesgcm():  # type: ignore
    """Lazy import so module-level import failure doesn't break tests."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore
    return AESGCM


def encrypt(plaintext: str) -> tuple[bytes, bytes]:
    """Encrypt a plaintext API key. Returns (ciphertext, nonce)."""
    import secrets

    key = _load_key()
    nonce = secrets.token_bytes(12)  # GCM standard 96-bit nonce
    AESGCM = _aesgcm()
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return ciphertext, nonce


def decrypt(ciphertext_b64: str, nonce_b64: str) -> str:
    """
    Decrypt a stored API key.

    Supabase returns bytea columns as base64 strings via the REST API.
    Both ciphertext and nonce are passed as base64-encoded values.
    """
    key = _load_key()
    ciphertext = base64.b64decode(ciphertext_b64)
    nonce = base64.b64decode(nonce_b64)
    AESGCM = _aesgcm()
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    return plaintext.decode()
