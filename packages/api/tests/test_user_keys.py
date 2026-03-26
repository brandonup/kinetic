"""
Tests for app/services/user_keys.py — BYOK key fetch/decrypt helpers.

Covers:
  - to_bytes: all three input forms (raw bytes, \\x-prefixed string, plain hex string)
  - fetch_user_key: successful decrypt, no row found, decrypt failure (silent None)
  - Encryption round-trip: keys stored with \\x prefix (profile.py post-KIN-397 fix)
    decrypt correctly — this is the regression test that would have caught KIN-397.
  - Negative: keys stored without \\x prefix (old broken format) return None gracefully

KIN-397: KB upload pipeline returned None from fetch_user_key because profile.py
stored ciphertext.hex() without the \\x prefix, causing PostgREST to store the
hex characters as ASCII bytes. decrypt_api_key received wrong bytes → InvalidTag
→ silently swallowed → None returned → documents endpoint raised 400.
"""

from __future__ import annotations

import base64
import os
from unittest.mock import MagicMock, patch

import pytest

from app.services.encryption import decrypt_api_key, encrypt_api_key
from app.services.user_keys import fetch_user_key, to_bytes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TEST_PROVIDER = "openai"
TEST_API_KEY = "sk-openai-testkey12345abcdef"

# Stable 32-byte master key for deterministic tests
_MASTER_KEY_BYTES = b"A" * 32
_MASTER_KEY_B64 = base64.b64encode(_MASTER_KEY_BYTES).decode()


def _make_supabase_mock(ciphertext_val, nonce_val) -> MagicMock:
    """Return a mock Supabase client whose user_api_keys query returns given values."""
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
        data={"key_ciphertext": ciphertext_val, "key_nonce": nonce_val}
    )
    return mock


def _make_empty_supabase_mock() -> MagicMock:
    """Return a mock Supabase client that returns no row (no key saved)."""
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
        data=None
    )
    return mock


# ---------------------------------------------------------------------------
# TestToBytes
# ---------------------------------------------------------------------------


class TestToBytes:
    """to_bytes converts Supabase bytea return values to Python bytes."""

    def test_raw_bytes_passthrough(self):
        raw = b"\xde\xad\xbe\xef"
        assert to_bytes(raw) == b"\xde\xad\xbe\xef"

    def test_bytearray_converted_to_bytes(self):
        raw = bytearray(b"\x01\x02\x03")
        result = to_bytes(raw)
        assert isinstance(result, bytes)
        assert result == b"\x01\x02\x03"

    def test_backslash_x_prefixed_hex_string(self):
        # PostgREST may return bytea as '\\xdeadbeef' string in some configs
        assert to_bytes("\\xdeadbeef") == b"\xde\xad\xbe\xef"

    def test_plain_hex_string_decoded(self):
        # Legacy path — plain hex string without prefix
        assert to_bytes("deadbeef") == b"\xde\xad\xbe\xef"

    def test_empty_bytes_passthrough(self):
        assert to_bytes(b"") == b""


# ---------------------------------------------------------------------------
# TestEncryptionRoundTrip — regression for KIN-397
# ---------------------------------------------------------------------------


class TestEncryptionRoundTrip:
    """
    Regression tests for the KIN-397 bytea encoding bug.

    When profile.py correctly stores '\\x' + ciphertext.hex() (post-fix),
    PostgREST stores actual binary bytes. The Supabase client returns them
    as raw Python bytes. fetch_user_key must decrypt correctly.

    Before the fix: profile.py stored ciphertext.hex() without the prefix.
    PostgREST stored ASCII characters. Supabase returned bytes of ASCII
    characters. decrypt_api_key received wrong input → InvalidTag → None.
    """

    def test_correct_format_decrypts_successfully(self):
        """
        Simulates the post-fix path: keys stored with \\x prefix come back
        as binary bytes → decrypt succeeds.
        """
        with patch("app.services.user_keys.load_master_key", return_value=_MASTER_KEY_BYTES):
            ciphertext, nonce = encrypt_api_key(TEST_API_KEY, _MASTER_KEY_BYTES, TEST_USER_ID)

            # Simulate Supabase returning raw binary bytes (correct \\x-prefix storage)
            mock_client = _make_supabase_mock(
                ciphertext_val=ciphertext,   # raw bytes — what PostgREST returns for bytea
                nonce_val=nonce,
            )

            result = fetch_user_key(mock_client, TEST_USER_ID, TEST_PROVIDER)

        assert result == TEST_API_KEY

    def test_wrong_format_returns_none_gracefully(self):
        """
        Simulates the pre-fix (broken) path: ciphertext stored as ASCII hex
        characters (i.e., ciphertext.hex() without \\x prefix → PostgREST
        stored 'deadbeef' as bytes b'd','e','a','d','b','e','e','f').
        fetch_user_key should return None, not raise.
        """
        with patch("app.services.user_keys.load_master_key", return_value=_MASTER_KEY_BYTES):
            ciphertext, nonce = encrypt_api_key(TEST_API_KEY, _MASTER_KEY_BYTES, TEST_USER_ID)

            # Simulate old broken format: ASCII hex characters stored as bytes
            broken_ciphertext_bytes = ciphertext.hex().encode("ascii")
            broken_nonce_bytes = nonce.hex().encode("ascii")

            mock_client = _make_supabase_mock(
                ciphertext_val=broken_ciphertext_bytes,
                nonce_val=broken_nonce_bytes,
            )

            result = fetch_user_key(mock_client, TEST_USER_ID, TEST_PROVIDER)

        assert result is None  # InvalidTag silently caught

    def test_backslash_x_string_also_decrypts(self):
        """
        If Supabase ever returns bytea as '\\x{hex}' string form,
        to_bytes handles it and decryption still succeeds.
        """
        with patch("app.services.user_keys.load_master_key", return_value=_MASTER_KEY_BYTES):
            ciphertext, nonce = encrypt_api_key(TEST_API_KEY, _MASTER_KEY_BYTES, TEST_USER_ID)

            # Simulate PostgREST returning '\\x{hex}' string
            mock_client = _make_supabase_mock(
                ciphertext_val="\\x" + ciphertext.hex(),
                nonce_val="\\x" + nonce.hex(),
            )

            result = fetch_user_key(mock_client, TEST_USER_ID, TEST_PROVIDER)

        assert result == TEST_API_KEY

    def test_different_users_cannot_decrypt_each_others_keys(self):
        """Per-user HKDF derivation: user B's key cannot decrypt user A's ciphertext."""
        user_a = "00000000-0000-0000-0000-000000000001"
        user_b = "00000000-0000-0000-0000-000000000002"

        with patch("app.services.user_keys.load_master_key", return_value=_MASTER_KEY_BYTES):
            ciphertext_a, nonce_a = encrypt_api_key(TEST_API_KEY, _MASTER_KEY_BYTES, user_a)

            # Return user A's encrypted bytes but query for user B
            mock_client = _make_supabase_mock(
                ciphertext_val=ciphertext_a,
                nonce_val=nonce_a,
            )
            # fetch_user_key will decrypt using user_b's derived key → InvalidTag → None
            result = fetch_user_key(mock_client, user_b, TEST_PROVIDER)

        assert result is None


# ---------------------------------------------------------------------------
# TestFetchUserKey
# ---------------------------------------------------------------------------


class TestFetchUserKey:
    """fetch_user_key behavior: no key, success, decrypt failure."""

    def test_no_key_saved_returns_none(self):
        mock_client = _make_empty_supabase_mock()
        with patch("app.services.user_keys.load_master_key", return_value=_MASTER_KEY_BYTES):
            result = fetch_user_key(mock_client, TEST_USER_ID, TEST_PROVIDER)
        assert result is None

    def test_returns_decrypted_plaintext(self):
        with patch("app.services.user_keys.load_master_key", return_value=_MASTER_KEY_BYTES):
            ciphertext, nonce = encrypt_api_key(TEST_API_KEY, _MASTER_KEY_BYTES, TEST_USER_ID)
            mock_client = _make_supabase_mock(ciphertext, nonce)
            result = fetch_user_key(mock_client, TEST_USER_ID, TEST_PROVIDER)
        assert result == TEST_API_KEY

    def test_decrypt_failure_logs_and_returns_none(self, caplog):
        """Corrupted ciphertext triggers InvalidTag → logged at ERROR → None returned."""
        import logging

        with patch("app.services.user_keys.load_master_key", return_value=_MASTER_KEY_BYTES):
            # Provide junk bytes that will never decrypt
            mock_client = _make_supabase_mock(
                ciphertext_val=b"\x00" * 32,
                nonce_val=b"\x01" * 12,
            )
            with caplog.at_level(logging.ERROR, logger="app.services.user_keys"):
                result = fetch_user_key(mock_client, TEST_USER_ID, TEST_PROVIDER)

        assert result is None
        assert any("Failed to decrypt" in r.message for r in caplog.records)

    def test_missing_master_key_returns_none(self, caplog):
        """RuntimeError from load_master_key is swallowed → None."""
        import logging

        with patch(
            "app.services.user_keys.load_master_key",
            side_effect=RuntimeError("API_KEY_ENCRYPTION_KEY not set"),
        ):
            with patch("app.services.user_keys.load_master_key", side_effect=RuntimeError("not set")):
                ciphertext, nonce = b"\x00" * 32, b"\x00" * 12
                mock_client = _make_supabase_mock(ciphertext, nonce)
                with caplog.at_level(logging.ERROR, logger="app.services.user_keys"):
                    result = fetch_user_key(mock_client, TEST_USER_ID, TEST_PROVIDER)

        assert result is None


# ---------------------------------------------------------------------------
# TestProfileStoresBytesWithPrefix — KIN-397 regression (write-path)
# ---------------------------------------------------------------------------


class TestProfileStoresBytesWithPrefix:
    """
    Verifies that the profile upsert route stores bytea values with \\x prefix.
    This is the write-path regression test for KIN-397.

    Uses the shared `client` fixture (dependency_overrides for auth, no real DB).
    """

    def test_upsert_stores_ciphertext_with_backslash_x_prefix(self, client):
        """
        The upsert call must include '\\x' prefixed hex strings for
        key_ciphertext and key_nonce so PostgREST stores binary bytes.
        Without this prefix, PostgREST stores ASCII characters, breaking decryption.
        """
        upsert_call_kwargs: dict = {}

        mock_db = MagicMock()

        def capture_upsert(row, **kwargs):
            upsert_call_kwargs.update(row)
            result_mock = MagicMock()
            result_mock.execute.return_value = MagicMock(
                data=[{"provider": "openai", "key_hint": "sk-open...4321"}]
            )
            return result_mock

        mock_db.table.return_value.upsert = capture_upsert

        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.post(
                "/api/v1/profile/api-keys",
                json={"provider": "openai", "api_key": "sk-openai-testkey12345abcdef"},
            )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert upsert_call_kwargs.get("key_ciphertext", "").startswith("\\x"), (
            "key_ciphertext must be prefixed with \\x so PostgREST stores binary bytes. "
            "Without this prefix, PostgREST stores ASCII characters, breaking decryption (KIN-397)."
        )
        assert upsert_call_kwargs.get("key_nonce", "").startswith("\\x"), (
            "key_nonce must be prefixed with \\x (KIN-397)."
        )
