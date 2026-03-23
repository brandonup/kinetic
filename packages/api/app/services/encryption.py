"""
API Key Encryption Utilities — KIN-261.

Implements AES-256-GCM encryption for user LLM provider API keys.
Spec: docs/api-key-encryption-spec.md

Key derivation: HKDF-SHA256 with user_id as info parameter.
Nonce: 12-byte random, fresh per encryption call.
Master key: loaded from API_KEY_ENCRYPTION_KEY env var (32-byte base64).

Schema ref: docs/db-schema-spec.md §2 (user_api_keys: key_ciphertext, key_nonce, key_hint)
"""

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings


def load_master_key() -> bytes:
    """
    Load the AES-256-GCM master key from settings.

    Returns:
        32-byte master key.

    Raises:
        RuntimeError: Key is missing or not exactly 32 bytes.
    """
    raw = settings.API_KEY_ENCRYPTION_KEY
    if not raw:
        raise RuntimeError(
            "API_KEY_ENCRYPTION_KEY not set. "
            "Generate with: python -c \"import os, base64; print(base64.b64encode(os.urandom(32)).decode())\""
        )
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError(
            f"API_KEY_ENCRYPTION_KEY must be 32 bytes after base64 decode, got {len(key)}"
        )
    return key


def derive_user_key(master_key: bytes, user_id: str) -> bytes:
    """
    Derive a per-user 256-bit encryption key from the master key using HKDF-SHA256.

    Per-user derivation limits blast radius: one extracted derived key cannot
    decrypt another user's keys. User ID is the HKDF info parameter.

    Args:
        master_key: 32-byte master key from load_master_key().
        user_id: The user's UUID string (from public.users.id).

    Returns:
        32-byte derived key for this user.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,  # master_key is already high-entropy
        info=user_id.encode("utf-8"),
    )
    return hkdf.derive(master_key)


def encrypt_api_key(plaintext_key: str, master_key: bytes, user_id: str) -> tuple[bytes, bytes]:
    """
    Encrypt a plaintext API key with AES-256-GCM.

    Args:
        plaintext_key: The provider API key in plaintext.
        master_key: 32-byte master key from load_master_key().
        user_id: Used to derive a per-user encryption key.

    Returns:
        Tuple of (ciphertext: bytes, nonce: bytes). Both must be stored.
        The nonce is 12 bytes (96-bit), fresh per call.
    """
    derived_key = derive_user_key(master_key, user_id)
    aesgcm = AESGCM(derived_key)
    nonce = os.urandom(12)  # 96-bit, standard for GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext_key.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_api_key(ciphertext: bytes, nonce: bytes, master_key: bytes, user_id: str) -> str:
    """
    Decrypt an AES-256-GCM encrypted API key.

    Args:
        ciphertext: Encrypted key bytes (from key_ciphertext column).
        nonce: GCM nonce bytes (from key_nonce column).
        master_key: 32-byte master key from load_master_key().
        user_id: Must match the user_id used during encryption.

    Returns:
        Plaintext API key string.

    Raises:
        cryptography.exceptions.InvalidTag: If key or nonce do not match — authentication failure.
    """
    derived_key = derive_user_key(master_key, user_id)
    aesgcm = AESGCM(derived_key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def mask_api_key(key: str) -> str:
    """
    Return a safe display hint for a provider API key.

    Format: first 7 chars + "..." + last 4 chars.
    If the key is shorter than 12 characters, returns "***...***".

    The masked value is stored at write time in key_hint (db-schema-spec §2).
    The plaintext key is discarded after masking and encryption.

    Args:
        key: Plaintext API key.

    Returns:
        Masked string safe for display in UI and logs.
    """
    if len(key) < 12:
        return "***...***"
    return f"{key[:7]}...{key[-4:]}"
