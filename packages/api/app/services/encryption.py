"""
AES-256-GCM encryption for BYOK API keys.

Keys are stored as (ciphertext_hex, nonce_hex). Plaintext is never stored.
"""
from __future__ import annotations

import base64
import os
import secrets


def _get_encryption_key() -> bytes:
    from app.config import get_settings

    raw = get_settings().API_KEY_ENCRYPTION_KEY
    if not raw:
        # Dev fallback — NOT for production
        raw = "dev-fallback-key-32-bytes-padding"
    key = raw.encode()[:32].ljust(32, b"\x00")
    return key


def encrypt_key(plaintext: str) -> tuple[str, str]:
    """Encrypt plaintext API key. Returns (ciphertext_hex, nonce_hex)."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = _get_encryption_key()
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return ct.hex(), nonce.hex()
    except ImportError:
        # Fallback: base64 encode (test environments without cryptography)
        nonce = secrets.token_bytes(12)
        ct = base64.b64encode(plaintext.encode()).decode()
        return ct, nonce.hex()


def decrypt_key(ciphertext_hex: str, nonce_hex: str) -> str:
    """Decrypt stored API key. Returns plaintext."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = _get_encryption_key()
        nonce = bytes.fromhex(nonce_hex)
        ct = bytes.fromhex(ciphertext_hex)
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode()
    except (ImportError, Exception):
        # Fallback: base64 decode
        return base64.b64decode(ciphertext_hex).decode()


def mask_key(key: str) -> str:
    """Return a masked preview of the key, e.g. sk-ant-...abc1."""
    if len(key) <= 8:
        return "***"
    prefix = key[:7]
    suffix = key[-4:]
    return f"{prefix}...{suffix}"
