"""Route tests for User Profile + API Key management — KIN-278 (KIN-261)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.conftest import TEST_USER_ID, ok, empty, seq


USER_ROW = {
    "id": TEST_USER_ID,
    "name": "Test User",
    "bio": "Software engineer",
    "role": "user",
    "default_model_id": None,
    "active_company_id": None,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

KEY_ROW = {
    "id": "key-1",
    "provider": "anthropic",
    "key_hint": "sk-ant-...abc1",
    "validated_at": None,
    "created_at": "2026-01-01T00:00:00Z",
}


class TestGetProfile:
    def test_returns_profile(self, client, sb):
        sb.execute.return_value = ok(USER_ROW)
        r = client.get("/api/v1/profile")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == TEST_USER_ID
        # bio is present but never a raw key
        assert "bio" in data

    def test_not_found_returns_404(self, client, sb):
        sb.execute.return_value = empty()
        r = client.get("/api/v1/profile")
        assert r.status_code == 404


class TestUpdateProfile:
    def test_update_name(self, client, sb):
        updated = {**USER_ROW, "name": "New Name"}
        sb.execute.return_value = ok([updated])
        r = client.patch("/api/v1/profile", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_bio_too_long_returns_422(self, client, sb):
        r = client.patch("/api/v1/profile", json={"bio": "x" * 1001})
        assert r.status_code == 422

    def test_no_updates_returns_current_profile(self, client, sb):
        sb.execute.return_value = ok(USER_ROW)
        r = client.patch("/api/v1/profile", json={})
        assert r.status_code == 200


class TestUpsertApiKey:
    def test_stores_key_returns_hint_not_plaintext(self, client, sb):
        stored = {**KEY_ROW, "key_ciphertext": "DEADBEEF", "key_nonce": "00"}
        sb.execute.return_value = ok([stored])
        with patch("app.services.encryption.encrypt_key", return_value=("DEADBEEF", "00")), \
             patch("app.services.encryption.mask_key", return_value="sk-ant-...abc1"):
            r = client.put(
                "/api/v1/profile/api-keys/anthropic",
                json={"provider": "anthropic", "key": "sk-ant-test-key-1234567890abcdef"},
            )
        assert r.status_code == 200
        data = r.json()
        # Plaintext and ciphertext must NOT appear in response
        assert "key_ciphertext" not in data
        assert "key_nonce" not in data
        assert "key_hint" in data
        # The actual key value must not be in the response
        assert "sk-ant-test-key" not in str(data)

    def test_invalid_provider_returns_422(self, client, sb):
        r = client.put(
            "/api/v1/profile/api-keys/invalid_provider",
            json={"provider": "invalid_provider", "key": "somekey"},
        )
        assert r.status_code in (400, 422)

    def test_empty_key_returns_422(self, client, sb):
        r = client.put(
            "/api/v1/profile/api-keys/openai",
            json={"provider": "openai", "key": "   "},
        )
        assert r.status_code == 422

    def test_upsert_failure_returns_400(self, client, sb):
        sb.execute.return_value = empty()
        with patch("app.services.encryption.encrypt_key", return_value=("DEADBEEF", "00")), \
             patch("app.services.encryption.mask_key", return_value="sk-...1234"):
            r = client.put(
                "/api/v1/profile/api-keys/openai",
                json={"provider": "openai", "key": "sk-valid-key"},
            )
        assert r.status_code == 400


class TestListApiKeys:
    def test_returns_keys_without_plaintext(self, client, sb):
        sb.execute.return_value = ok([KEY_ROW])
        r = client.get("/api/v1/profile/api-keys")
        assert r.status_code == 200
        keys = r.json()
        assert len(keys) == 1
        # Confirm no ciphertext in any key row
        for k in keys:
            assert "key_ciphertext" not in k
            assert "key_nonce" not in k

    def test_empty_list(self, client, sb):
        sb.execute.return_value = ok([])
        r = client.get("/api/v1/profile/api-keys")
        assert r.status_code == 200
        assert r.json() == []


class TestDeleteApiKey:
    def test_success(self, client, sb):
        sb.execute.return_value = ok([])
        r = client.delete("/api/v1/profile/api-keys/anthropic")
        assert r.status_code == 204
