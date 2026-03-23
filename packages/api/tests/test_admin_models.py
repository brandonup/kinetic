"""Route tests for Admin LLM Model management — KIN-278 (KIN-265)."""
from __future__ import annotations

import pytest

from tests.conftest import TEST_MODEL_ID, ok, empty, seq


MODEL_ROW = {
    "id": TEST_MODEL_ID,
    "provider": "anthropic",
    "model_id": "claude-sonnet-4-6",
    "display_name": "Claude Sonnet 4.6",
    "category": "generation",
    "enabled": True,
    "context_window": 200_000,
    "created_at": "2026-01-01T00:00:00Z",
}


class TestListModels:
    def test_requires_admin(self, client, sb):
        r = client.get("/api/v1/admin/models")
        assert r.status_code == 403

    def test_admin_lists_all(self, admin_client, sb):
        sb.execute.return_value = ok([MODEL_ROW])
        r = admin_client.get("/api/v1/admin/models")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_filter_by_category(self, admin_client, sb):
        sb.execute.return_value = ok([MODEL_ROW])
        r = admin_client.get("/api/v1/admin/models?category=generation")
        assert r.status_code == 200


class TestCreateModel:
    def test_success(self, admin_client, sb):
        sb.execute.return_value = ok([MODEL_ROW])
        r = admin_client.post(
            "/api/v1/admin/models",
            json={
                "provider": "anthropic",
                "model_id": "claude-sonnet-4-6",
                "display_name": "Claude Sonnet 4.6",
                "category": "generation",
                "enabled": True,
                "context_window": 200_000,
            },
        )
        assert r.status_code == 201
        assert r.json()["model_id"] == "claude-sonnet-4-6"

    def test_invalid_category_returns_422(self, admin_client, sb):
        r = admin_client.post(
            "/api/v1/admin/models",
            json={
                "provider": "anthropic",
                "model_id": "foo",
                "display_name": "Foo",
                "category": "invalid_cat",
            },
        )
        assert r.status_code == 422

    def test_requires_admin(self, client, sb):
        r = client.post(
            "/api/v1/admin/models",
            json={
                "provider": "openai",
                "model_id": "gpt-4",
                "display_name": "GPT-4",
                "category": "generation",
            },
        )
        assert r.status_code == 403

    def test_insert_failure_returns_400(self, admin_client, sb):
        sb.execute.return_value = empty()
        r = admin_client.post(
            "/api/v1/admin/models",
            json={
                "provider": "openai",
                "model_id": "gpt-4",
                "display_name": "GPT-4",
                "category": "generation",
            },
        )
        assert r.status_code == 400


class TestUpdateModel:
    def test_enable_disable(self, admin_client, sb):
        updated = {**MODEL_ROW, "enabled": False}
        seq(sb, ok(MODEL_ROW), ok([updated]))
        r = admin_client.patch(f"/api/v1/admin/models/{TEST_MODEL_ID}", json={"enabled": False})
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_not_found(self, admin_client, sb):
        seq(sb, empty())
        r = admin_client.patch(f"/api/v1/admin/models/{TEST_MODEL_ID}", json={"enabled": True})
        assert r.status_code == 404

    def test_requires_admin(self, client, sb):
        r = client.patch(f"/api/v1/admin/models/{TEST_MODEL_ID}", json={"enabled": False})
        assert r.status_code == 403


class TestDeleteModel:
    def test_success(self, admin_client, sb):
        seq(sb, ok(MODEL_ROW), ok([]))
        r = admin_client.delete(f"/api/v1/admin/models/{TEST_MODEL_ID}")
        assert r.status_code == 204

    def test_not_found(self, admin_client, sb):
        seq(sb, empty())
        r = admin_client.delete(f"/api/v1/admin/models/{TEST_MODEL_ID}")
        assert r.status_code == 404

    def test_requires_admin(self, client, sb):
        r = client.delete(f"/api/v1/admin/models/{TEST_MODEL_ID}")
        assert r.status_code == 403
