"""
Tests for Admin LLM Models tab — KIN-265 / KIN-278.

Covers:
  - POST   /api/v1/admin/models           (add model)
  - GET    /api/v1/admin/models           (list all models)
  - PATCH  /api/v1/admin/models/{id}/enable
  - PATCH  /api/v1/admin/models/{id}/disable
  - DELETE /api/v1/admin/models/{id}
  - GET    /api/v1/models                 (user-facing: generation only, enabled only)
  - Cache invalidation on enable/disable
  - Admin-only enforcement on all admin endpoints
"""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_model(admin_client, model_id, category="generation", enabled=True):
    resp = admin_client.post(
        "/api/v1/admin/models",
        json={
            "model_id": model_id,
            "provider": "openai",
            "category": category,
            "display_name": model_id,
            "context_window": 128000,
            "enabled": enabled,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/v1/admin/models
# ---------------------------------------------------------------------------

class TestAddModel:
    def test_add_generation_model(self, admin_client):
        resp = admin_client.post(
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
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["model_id"] == "gpt-4o"
        assert data["category"] == "generation"

    def test_add_embedding_model(self, admin_client):
        resp = admin_client.post(
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
        assert resp.status_code in (200, 201)
        assert resp.json()["category"] == "embedding"

    def test_add_reranking_model(self, admin_client):
        resp = admin_client.post(
            "/api/v1/admin/models",
            json={
                "model_id": "rerank-english-v3.0",
                "provider": "cohere",
                "category": "reranking",
                "display_name": "Cohere Rerank v3",
                "context_window": 4096,
                "enabled": True,
            },
        )
        assert resp.status_code in (200, 201)
        assert resp.json()["category"] == "reranking"

    def test_model_id_required(self, admin_client):
        resp = admin_client.post(
            "/api/v1/admin/models",
            json={"provider": "openai", "category": "generation"},
        )
        assert resp.status_code == 422

    def test_invalid_category_rejected(self, admin_client):
        resp = admin_client.post(
            "/api/v1/admin/models",
            json={
                "model_id": "mystery-model",
                "provider": "openai",
                "category": "unknown_category",
                "display_name": "Mystery",
                "context_window": 4096,
            },
        )
        assert resp.status_code == 422

    def test_non_admin_returns_403(self, auth_client):
        resp = auth_client.post(
            "/api/v1/admin/models",
            json={
                "model_id": "gpt-4o",
                "provider": "openai",
                "category": "generation",
                "display_name": "GPT-4o",
                "context_window": 128000,
            },
        )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.post(
            "/api/v1/admin/models",
            json={
                "model_id": "gpt-4o",
                "provider": "openai",
                "category": "generation",
                "display_name": "GPT-4o",
                "context_window": 128000,
            },
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/admin/models
# ---------------------------------------------------------------------------

class TestListAdminModels:
    def test_lists_all_categories(self, admin_client):
        make_model(admin_client, "gpt-4o", category="generation")
        make_model(admin_client, "text-embedding-3-small", category="embedding")
        resp = admin_client.get("/api/v1/admin/models")
        assert resp.status_code == 200
        categories = {m["category"] for m in resp.json()}
        assert "generation" in categories
        assert "embedding" in categories

    def test_includes_disabled_models(self, admin_client):
        make_model(admin_client, "gpt-3.5-turbo", category="generation", enabled=False)
        resp = admin_client.get("/api/v1/admin/models")
        model_ids = [m["model_id"] for m in resp.json()]
        assert "gpt-3.5-turbo" in model_ids

    def test_non_admin_returns_403(self, auth_client):
        resp = auth_client.get("/api/v1/admin/models")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/v1/admin/models/{id}/enable
# ---------------------------------------------------------------------------

class TestEnableModel:
    def test_enable_disabled_model(self, admin_client):
        model = make_model(admin_client, "claude-3-haiku", enabled=False)
        resp = admin_client.patch(f"/api/v1/admin/models/{model['id']}/enable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_enable_already_enabled_is_idempotent(self, admin_client):
        model = make_model(admin_client, "claude-3-sonnet", enabled=True)
        resp = admin_client.patch(f"/api/v1/admin/models/{model['id']}/enable")
        assert resp.status_code == 200

    def test_non_admin_returns_403(self, auth_client, admin_client):
        model = make_model(admin_client, "some-model")
        resp = auth_client.patch(f"/api/v1/admin/models/{model['id']}/enable")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/v1/admin/models/{id}/disable
# ---------------------------------------------------------------------------

class TestDisableModel:
    def test_disable_enabled_model(self, admin_client):
        model = make_model(admin_client, "gpt-4-turbo", enabled=True)
        resp = admin_client.patch(f"/api/v1/admin/models/{model['id']}/disable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_disable_already_disabled_is_idempotent(self, admin_client):
        model = make_model(admin_client, "gpt-4-mini", enabled=False)
        resp = admin_client.patch(f"/api/v1/admin/models/{model['id']}/disable")
        assert resp.status_code == 200

    def test_non_admin_returns_403(self, auth_client, admin_client):
        model = make_model(admin_client, "to-disable-model")
        resp = auth_client.patch(f"/api/v1/admin/models/{model['id']}/disable")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/v1/admin/models/{id}
# ---------------------------------------------------------------------------

class TestDeleteModel:
    def test_delete_model(self, admin_client):
        model = make_model(admin_client, "delete-me-model")
        resp = admin_client.delete(f"/api/v1/admin/models/{model['id']}")
        assert resp.status_code in (200, 204)
        # Verify gone from admin list
        list_resp = admin_client.get("/api/v1/admin/models")
        ids = [m["id"] for m in list_resp.json()]
        assert model["id"] not in ids

    def test_delete_nonexistent_returns_404(self, admin_client):
        resp = admin_client.delete(
            "/api/v1/admin/models/00000000-0000-0000-0000-999999999999"
        )
        assert resp.status_code == 404

    def test_non_admin_returns_403(self, auth_client, admin_client):
        model = make_model(admin_client, "protected-model")
        resp = auth_client.delete(f"/api/v1/admin/models/{model['id']}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/models  (user-facing model selector)
# ---------------------------------------------------------------------------

class TestUserFacingModelSelector:
    def test_returns_only_generation_models(self, admin_client, auth_client):
        make_model(admin_client, "gen-model-a", category="generation", enabled=True)
        make_model(admin_client, "embed-model-a", category="embedding", enabled=True)
        make_model(admin_client, "rerank-model-a", category="reranking", enabled=True)

        resp = auth_client.get("/api/v1/models")
        assert resp.status_code == 200
        categories = {m["category"] for m in resp.json()}
        assert categories == {"generation"}, (
            f"User-facing selector leaked non-generation categories: {categories}"
        )

    def test_excludes_disabled_models(self, admin_client, auth_client):
        make_model(admin_client, "disabled-gen", category="generation", enabled=False)
        resp = auth_client.get("/api/v1/models")
        assert resp.status_code == 200
        model_ids = [m["model_id"] for m in resp.json()]
        assert "disabled-gen" not in model_ids

    def test_includes_enabled_generation_models(self, admin_client, auth_client):
        make_model(admin_client, "enabled-gen", category="generation", enabled=True)
        resp = auth_client.get("/api/v1/models")
        assert resp.status_code == 200
        model_ids = [m["model_id"] for m in resp.json()]
        assert "enabled-gen" in model_ids

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/v1/models")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------

class TestCacheInvalidation:
    def test_disabled_model_immediately_absent_from_user_selector(
        self, admin_client, auth_client
    ):
        model = make_model(admin_client, "cache-test-model", category="generation", enabled=True)

        # Confirm visible
        before = auth_client.get("/api/v1/models").json()
        assert any(m["model_id"] == "cache-test-model" for m in before)

        # Disable
        admin_client.patch(f"/api/v1/admin/models/{model['id']}/disable")

        # Must be absent immediately (cache invalidated)
        after = auth_client.get("/api/v1/models").json()
        assert not any(m["model_id"] == "cache-test-model" for m in after)

    def test_enabled_model_immediately_present_in_user_selector(
        self, admin_client, auth_client
    ):
        model = make_model(admin_client, "cache-enable-model", category="generation", enabled=False)

        # Confirm absent
        before = auth_client.get("/api/v1/models").json()
        assert not any(m["model_id"] == "cache-enable-model" for m in before)

        # Enable
        admin_client.patch(f"/api/v1/admin/models/{model['id']}/enable")

        # Must be present immediately
        after = auth_client.get("/api/v1/models").json()
        assert any(m["model_id"] == "cache-enable-model" for m in after)
