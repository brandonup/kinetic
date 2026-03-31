"""
Tests for KIN-261: User Profile CRUD

Covers:
  - Encryption utilities (TestEncryptionUtils)
  - Log scrub middleware (TestLogScrubMiddleware)
  - Profile endpoints (TestProfileEndpoints)
  - API key endpoints (TestApiKeyEndpoints)
  - Default model endpoint (TestDefaultModelEndpoint)

All Supabase calls are mocked. Uses client fixture from conftest.py.
Schema ref: docs/db-schema-spec.md §1 (users), §2 (user_api_keys)
"""

import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Test encryption key — 32 bytes, base64-encoded (matches conftest pattern)
# ---------------------------------------------------------------------------
TEST_USER_ID = str(uuid4())
TEST_MODEL_ID = str(uuid4())


# ---------------------------------------------------------------------------
# Task 1: Encryption utilities
# ---------------------------------------------------------------------------


class TestEncryptionUtils:
    """Tests for app.services.encryption — HKDF + AES-256-GCM per spec."""

    def test_load_master_key_returns_32_bytes(self):
        from app.services.encryption import load_master_key

        key = load_master_key()
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_load_master_key_raises_if_missing(self, monkeypatch):
        monkeypatch.delenv("API_KEY_ENCRYPTION_KEY", raising=False)
        from importlib import reload

        import app.services.encryption as enc_module

        # Patch settings to simulate missing key
        with patch.object(enc_module, "settings") as mock_settings:
            mock_settings.API_KEY_ENCRYPTION_KEY = ""
            with pytest.raises(RuntimeError, match="API_KEY_ENCRYPTION_KEY"):
                enc_module.load_master_key()

    def test_load_master_key_raises_if_wrong_length(self):
        from app.services.encryption import load_master_key

        bad_key = base64.b64encode(b"tooshort").decode()
        with patch("app.services.encryption.settings") as mock_settings:
            mock_settings.API_KEY_ENCRYPTION_KEY = bad_key
            with pytest.raises(RuntimeError, match="32 bytes"):
                load_master_key()

    def test_encrypt_decrypt_roundtrip(self):
        from app.services.encryption import decrypt_api_key, encrypt_api_key, load_master_key

        master = load_master_key()
        plaintext = "sk-ant-api03-abc123xyz"
        ciphertext, nonce = encrypt_api_key(plaintext, master, TEST_USER_ID)

        assert isinstance(ciphertext, bytes)
        assert isinstance(nonce, bytes)
        assert len(nonce) == 12
        assert ciphertext != plaintext.encode()

        recovered = decrypt_api_key(ciphertext, nonce, master, TEST_USER_ID)
        assert recovered == plaintext

    def test_different_nonce_each_call(self):
        from app.services.encryption import encrypt_api_key, load_master_key

        master = load_master_key()
        _, nonce1 = encrypt_api_key("sk-test", master, TEST_USER_ID)
        _, nonce2 = encrypt_api_key("sk-test", master, TEST_USER_ID)
        assert nonce1 != nonce2

    def test_different_user_produces_different_derived_key(self):
        from app.services.encryption import derive_user_key, load_master_key

        master = load_master_key()
        key1 = derive_user_key(master, str(uuid4()))
        key2 = derive_user_key(master, str(uuid4()))
        assert key1 != key2

    def test_wrong_user_id_cannot_decrypt(self):
        from cryptography.exceptions import InvalidTag

        from app.services.encryption import decrypt_api_key, encrypt_api_key, load_master_key

        master = load_master_key()
        ciphertext, nonce = encrypt_api_key("sk-secret", master, TEST_USER_ID)
        with pytest.raises(InvalidTag):
            decrypt_api_key(ciphertext, nonce, master, str(uuid4()))

    def test_mask_api_key_standard(self):
        from app.services.encryption import mask_api_key

        # "sk-ant-api03-abcXYZ" (19 chars): first 7 = "sk-ant-", last 4 = "cXYZ"
        assert mask_api_key("sk-ant-api03-abcXYZ") == "sk-ant-...cXYZ"

    def test_mask_api_key_openai(self):
        from app.services.encryption import mask_api_key

        assert mask_api_key("sk-proj-abcdefghij1234") == "sk-proj...1234"

    def test_mask_api_key_short(self):
        from app.services.encryption import mask_api_key

        assert mask_api_key("short") == "***...***"

    def test_mask_api_key_exactly_12_chars(self):
        from app.services.encryption import mask_api_key

        # 12 chars: first 7 + "..." + last 4
        key = "abcdefghijkl"  # 12 chars
        result = mask_api_key(key)
        assert result == "abcdefg...ijkl"


# ---------------------------------------------------------------------------
# Task 1b: Log scrub utilities
# ---------------------------------------------------------------------------


class TestLogScrubMiddleware:
    """Tests for app.middleware.log_scrub — sensitive field redaction."""

    def test_scrub_dict_redacts_api_key(self):
        from app.middleware.log_scrub import scrub_dict

        result = scrub_dict({"api_key": "sk-secret", "name": "Alice"})
        assert result["api_key"] == "[REDACTED]"
        assert result["name"] == "Alice"

    def test_scrub_dict_redacts_key_ciphertext(self):
        from app.middleware.log_scrub import scrub_dict

        result = scrub_dict({"key_ciphertext": b"bytes", "provider": "openai"})
        assert result["key_ciphertext"] == "[REDACTED]"
        assert result["provider"] == "openai"

    def test_scrub_dict_redacts_key_nonce(self):
        from app.middleware.log_scrub import scrub_dict

        result = scrub_dict({"key_nonce": b"nonce", "user_id": "abc"})
        assert result["key_nonce"] == "[REDACTED]"
        assert result["user_id"] == "abc"

    def test_scrub_dict_redacts_authorization(self):
        from app.middleware.log_scrub import scrub_dict

        result = scrub_dict({"authorization": "Bearer token123"})
        assert result["authorization"] == "[REDACTED]"

    def test_scrub_dict_redacts_nested(self):
        from app.middleware.log_scrub import scrub_dict

        result = scrub_dict({"outer": {"api_key": "secret", "safe": "value"}})
        assert result["outer"]["api_key"] == "[REDACTED]"
        assert result["outer"]["safe"] == "value"

    def test_scrub_dict_leaves_safe_fields(self):
        from app.middleware.log_scrub import scrub_dict

        payload = {"name": "Alice", "bio": "Engineer", "provider": "anthropic"}
        result = scrub_dict(payload)
        assert result == payload

    def test_scrub_dict_redacts_wildcard_secret(self):
        from app.middleware.log_scrub import scrub_dict

        result = scrub_dict({"my_secret": "topsecret"})
        assert result["my_secret"] == "[REDACTED]"

    def test_scrub_dict_redacts_wildcard_token(self):
        from app.middleware.log_scrub import scrub_dict

        result = scrub_dict({"access_token": "tok123"})
        assert result["access_token"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# Task 3: Profile endpoints
# ---------------------------------------------------------------------------


class TestProfileEndpoints:
    """Tests for GET/PATCH /api/v1/profile."""

    def _mock_supabase_user(self, user_data: dict):
        """Returns a mock that simulates supabase.table('users').select(...).eq(...).single().execute()."""
        mock = MagicMock()
        mock.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=user_data
        )
        mock.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[user_data]
        )
        return mock

    def test_get_profile_returns_profile(self, client):
        user_row = {
            "id": TEST_USER_ID,
            "name": "Alice",
            "email": "alice@example.com",
            "bio": "Engineer",
            "default_model_id": None,
        }
        mock_db = self._mock_supabase_user(user_row)
        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.get("/api/v1/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Alice"
        assert data["bio"] == "Engineer"
        # Ciphertext and nonce must never appear
        assert "key_ciphertext" not in data
        assert "key_nonce" not in data

    def test_get_profile_404_when_no_user(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.get("/api/v1/profile")
        assert response.status_code == 404

    def test_patch_profile_updates_name_and_bio(self, client):
        updated = {"id": TEST_USER_ID, "name": "Bob", "email": "bob@example.com", "bio": "Updated", "default_model_id": None}
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[updated]
        )
        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.patch(
                "/api/v1/profile", json={"name": "Bob", "bio": "Updated"}
            )
        assert response.status_code == 200
        assert response.json()["name"] == "Bob"

    def test_patch_profile_rejects_bio_over_1000_chars(self, client):
        # Pydantic field_validator raises ValueError → FastAPI returns 422 Unprocessable Entity
        with patch("app.api.routes.profile.get_supabase_client", return_value=MagicMock()):
            response = client.patch(
                "/api/v1/profile", json={"bio": "x" * 1001}
            )
        assert response.status_code == 422


class TestApiKeyEndpoints:
    """Tests for GET/POST/DELETE /api/v1/profile/api-keys."""

    def test_list_api_keys_never_returns_ciphertext(self, client):
        rows = [
            {
                "provider": "anthropic",
                "key_hint": "sk-ant-...abc1",
                "validated_at": None,
            }
        ]
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=rows
        )
        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.get("/api/v1/profile/api-keys")
        assert response.status_code == 200
        for item in response.json():
            assert "key_ciphertext" not in item
            assert "key_nonce" not in item

    def test_upsert_api_key_returns_hint_only(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"provider": "anthropic", "key_hint": "sk-ant-...bcd2"}]
        )
        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.post(
                "/api/v1/profile/api-keys",
                json={"provider": "anthropic", "api_key": "sk-ant-api03-testkey12345"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "key_ciphertext" not in data
        assert "key_nonce" not in data
        assert "key_hint" in data

    def test_upsert_api_key_invalid_provider(self, client):
        with patch("app.api.routes.profile.get_supabase_client", return_value=MagicMock()):
            response = client.post(
                "/api/v1/profile/api-keys",
                json={"provider": "invalid_provider", "api_key": "sk-test"},
            )
        assert response.status_code == 422

    def test_delete_api_key_success(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": str(uuid4())}]
        )
        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.delete("/api/v1/profile/api-keys/anthropic")
        assert response.status_code == 204

    def test_delete_api_key_not_found(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.delete("/api/v1/profile/api-keys/anthropic")
        assert response.status_code == 404


class TestDefaultModelEndpoint:
    """Tests for PATCH /api/v1/profile/default-model."""

    def test_set_default_model_success(self, client):
        model_row = {
            "id": TEST_MODEL_ID,
            "enabled": True,
            "category": "generation",
        }
        mock_db = MagicMock()
        # model lookup
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=model_row
        )
        # user update
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": TEST_USER_ID, "default_model_id": TEST_MODEL_ID}]
        )
        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.patch(
                "/api/v1/profile/default-model", json={"model_id": TEST_MODEL_ID}
            )
        assert response.status_code == 200

    def test_set_default_model_not_found(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.patch(
                "/api/v1/profile/default-model", json={"model_id": str(uuid4())}
            )
        assert response.status_code == 404

    def test_set_default_model_disabled_returns_404(self, client):
        model_row = {"id": TEST_MODEL_ID, "enabled": False, "category": "generation"}
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=model_row
        )
        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.patch(
                "/api/v1/profile/default-model", json={"model_id": TEST_MODEL_ID}
            )
        assert response.status_code == 404

    def test_set_default_model_wrong_category_returns_404(self, client):
        model_row = {"id": TEST_MODEL_ID, "enabled": True, "category": "embedding"}
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=model_row
        )
        with patch("app.api.routes.profile.get_supabase_client", return_value=mock_db):
            response = client.patch(
                "/api/v1/profile/default-model", json={"model_id": TEST_MODEL_ID}
            )
        assert response.status_code == 404
