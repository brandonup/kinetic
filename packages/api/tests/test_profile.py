"""
Tests for User Profile CRUD — KIN-261 / KIN-278.

Covers:
  - GET /api/v1/profile
  - PATCH /api/v1/profile
  - GET/POST/DELETE /api/v1/profile/api-keys
  - PATCH /api/v1/profile/default-model
"""

import pytest


# ---------------------------------------------------------------------------
# GET /api/v1/profile
# ---------------------------------------------------------------------------

class TestGetProfile:
    def test_returns_correct_fields(self, auth_client):
        resp = auth_client.get("/api/v1/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "name" in data
        assert "bio" in data
        assert "default_model_id" in data

    def test_api_keys_never_plaintext(self, auth_client):
        # Add a key first
        auth_client.post(
            "/api/v1/profile/api-keys",
            json={"provider": "openai", "key": "sk-supersecretvalue12345"},
        )
        resp = auth_client.get("/api/v1/profile")
        assert resp.status_code == 200
        # The raw key value must not appear anywhere in the response
        assert "sk-supersecretvalue12345" not in resp.text

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/v1/profile")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/profile
# ---------------------------------------------------------------------------

class TestPatchProfile:
    def test_update_name(self, auth_client):
        resp = auth_client.patch("/api/v1/profile", json={"name": "Jane Doe"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Jane Doe"

    def test_update_bio(self, auth_client):
        resp = auth_client.patch("/api/v1/profile", json={"bio": "Short bio."})
        assert resp.status_code == 200
        assert resp.json()["bio"] == "Short bio."

    def test_bio_at_limit_accepted(self, auth_client):
        bio = "x" * 1000
        resp = auth_client.patch("/api/v1/profile", json={"bio": bio})
        assert resp.status_code == 200

    def test_bio_over_limit_rejected(self, auth_client):
        bio = "x" * 1001
        resp = auth_client.patch("/api/v1/profile", json={"bio": bio})
        assert resp.status_code == 422

    def test_partial_update_preserves_other_fields(self, auth_client):
        auth_client.patch("/api/v1/profile", json={"name": "Alice", "bio": "Bio text."})
        resp = auth_client.patch("/api/v1/profile", json={"name": "Alice Updated"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Alice Updated"
        assert data["bio"] == "Bio text."

    def test_unauthenticated_returns_401(self, client):
        resp = client.patch("/api/v1/profile", json={"name": "X"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/profile/api-keys
# ---------------------------------------------------------------------------

class TestAddApiKey:
    def test_add_key_returns_masked_hint(self, auth_client):
        resp = auth_client.post(
            "/api/v1/profile/api-keys",
            json={"provider": "anthropic", "key": "sk-ant-secret9999"},
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "hint" in data
        # Plaintext key must never appear
        assert "sk-ant-secret9999" not in resp.text

    def test_add_key_hint_is_masked(self, auth_client):
        resp = auth_client.post(
            "/api/v1/profile/api-keys",
            json={"provider": "openai", "key": "sk-openai-abc123xyz"},
        )
        assert resp.status_code in (200, 201)
        hint = resp.json()["hint"]
        # Hint should be short and contain masking characters
        assert len(hint) < len("sk-openai-abc123xyz")
        assert "•" in hint or "..." in hint or "*" in hint

    def test_update_existing_key(self, auth_client):
        auth_client.post(
            "/api/v1/profile/api-keys",
            json={"provider": "openai", "key": "sk-first-key"},
        )
        resp = auth_client.post(
            "/api/v1/profile/api-keys",
            json={"provider": "openai", "key": "sk-second-key"},
        )
        assert resp.status_code in (200, 201)
        # Only one entry for the provider should exist
        keys_resp = auth_client.get("/api/v1/profile/api-keys")
        providers = [k["provider"] for k in keys_resp.json()]
        assert providers.count("openai") == 1

    def test_missing_provider_returns_422(self, auth_client):
        resp = auth_client.post(
            "/api/v1/profile/api-keys",
            json={"key": "sk-no-provider"},
        )
        assert resp.status_code == 422

    def test_missing_key_returns_422(self, auth_client):
        resp = auth_client.post(
            "/api/v1/profile/api-keys",
            json={"provider": "openai"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/profile/api-keys
# ---------------------------------------------------------------------------

class TestListApiKeys:
    def test_lists_configured_providers(self, auth_client):
        auth_client.post(
            "/api/v1/profile/api-keys",
            json={"provider": "anthropic", "key": "sk-ant-list-test"},
        )
        resp = auth_client.get("/api/v1/profile/api-keys")
        assert resp.status_code == 200
        providers = [k["provider"] for k in resp.json()]
        assert "anthropic" in providers

    def test_never_returns_plaintext_keys(self, auth_client):
        auth_client.post(
            "/api/v1/profile/api-keys",
            json={"provider": "groq", "key": "gsk-secret-groq-key-xyz"},
        )
        resp = auth_client.get("/api/v1/profile/api-keys")
        assert resp.status_code == 200
        assert "gsk-secret-groq-key-xyz" not in resp.text

    def test_returns_hint_per_key(self, auth_client):
        auth_client.post(
            "/api/v1/profile/api-keys",
            json={"provider": "google", "key": "AIza-google-key-secret"},
        )
        resp = auth_client.get("/api/v1/profile/api-keys")
        keys = resp.json()
        google_entry = next(k for k in keys if k["provider"] == "google")
        assert "hint" in google_entry


# ---------------------------------------------------------------------------
# DELETE /api/v1/profile/api-keys/{provider}
# ---------------------------------------------------------------------------

class TestDeleteApiKey:
    def test_delete_removes_key(self, auth_client):
        auth_client.post(
            "/api/v1/profile/api-keys",
            json={"provider": "openai", "key": "sk-to-delete"},
        )
        resp = auth_client.delete("/api/v1/profile/api-keys/openai")
        assert resp.status_code in (200, 204)
        keys_resp = auth_client.get("/api/v1/profile/api-keys")
        providers = [k["provider"] for k in keys_resp.json()]
        assert "openai" not in providers

    def test_delete_nonexistent_provider_returns_404(self, auth_client):
        resp = auth_client.delete("/api/v1/profile/api-keys/nonexistent_provider")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/profile/default-model
# ---------------------------------------------------------------------------

class TestDefaultModel:
    def test_set_valid_generation_model(self, auth_client, admin_client):
        # Ensure at least one generation model exists
        admin_client.post(
            "/api/v1/admin/models",
            json={
                "model_id": "gpt-4o",
                "provider": "openai",
                "category": "generation",
                "display_name": "GPT-4o",
                "context_window": 128000,
                "enabled": True,
            },
        )
        resp = auth_client.patch(
            "/api/v1/profile/default-model",
            json={"model_id": "gpt-4o"},
        )
        assert resp.status_code == 200
        assert resp.json()["default_model_id"] == "gpt-4o"

    def test_set_disabled_model_rejected(self, auth_client, admin_client):
        admin_client.post(
            "/api/v1/admin/models",
            json={
                "model_id": "gpt-3.5-turbo",
                "provider": "openai",
                "category": "generation",
                "display_name": "GPT-3.5 Turbo",
                "context_window": 16385,
                "enabled": False,
            },
        )
        resp = auth_client.patch(
            "/api/v1/profile/default-model",
            json={"model_id": "gpt-3.5-turbo"},
        )
        assert resp.status_code in (400, 422)

    def test_set_embedding_model_rejected(self, auth_client, admin_client):
        admin_client.post(
            "/api/v1/admin/models",
            json={
                "model_id": "text-embedding-3-small",
                "provider": "openai",
                "category": "embedding",
                "display_name": "text-embedding-3-small",
                "context_window": 8191,
                "enabled": True,
            },
        )
        resp = auth_client.patch(
            "/api/v1/profile/default-model",
            json={"model_id": "text-embedding-3-small"},
        )
        # Must reject non-generation models
        assert resp.status_code in (400, 422)

    def test_set_nonexistent_model_returns_404(self, auth_client):
        resp = auth_client.patch(
            "/api/v1/profile/default-model",
            json={"model_id": "does-not-exist"},
        )
        assert resp.status_code == 404
