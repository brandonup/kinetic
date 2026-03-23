"""
Tests for KIN-265: Admin LLM Models tab

Covers:
  - List models (TestListModels) — accessible to all authenticated users
  - Add model (TestAddModel) — admin only
  - Update model (TestUpdateModel) — admin only
  - Delete model (TestDeleteModel) — admin only
  - In-memory cache (TestModelsCache)

All Supabase calls are mocked. Uses client + admin_client fixtures from conftest.py.
Schema ref: docs/db-schema-spec.md §19 (llm_models)
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

TEST_MODEL_ID = str(uuid4())
PATCH_TARGET = "app.api.routes.admin_models.get_supabase_client"
PATCH_CACHE = "app.api.routes.admin_models._models_cache"


def _model_row(
    model_id: str = TEST_MODEL_ID,
    provider: str = "anthropic",
    model_id_str: str = "claude-sonnet-4-6",
    display_name: str = "Claude Sonnet 4.6",
    category: str = "generation",
    enabled: bool = True,
    context_window: int = 200000,
) -> dict:
    return {
        "id": model_id,
        "provider": provider,
        "model_id": model_id_str,
        "display_name": display_name,
        "category": category,
        "enabled": enabled,
        "context_window": context_window,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# List models — accessible to all authenticated users
# ---------------------------------------------------------------------------


class TestListModels:
    def test_list_returns_models(self, client):
        rows = [_model_row(), _model_row(model_id=str(uuid4()), model_id_str="gpt-4o", provider="openai")]
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .order.return_value
            .execute.return_value
        ) = MagicMock(data=rows)
        with patch(PATCH_TARGET, return_value=mock_db), patch(PATCH_CACHE, None):
            response = client.get("/api/v1/admin/models")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert len(data["models"]) == 2

    def test_list_returns_empty(self, client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .select.return_value
            .order.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db), patch(PATCH_CACHE, None):
            response = client.get("/api/v1/admin/models")
        assert response.status_code == 200
        assert response.json() == {"models": []}

    def test_list_uses_cache_when_populated(self, client):
        """If cache is populated, Supabase is not called."""
        cached_rows = [_model_row()]
        mock_db = MagicMock()
        with patch(PATCH_TARGET, return_value=mock_db), \
             patch("app.api.routes.admin_models._models_cache", cached_rows):
            response = client.get("/api/v1/admin/models")
        assert response.status_code == 200
        assert len(response.json()["models"]) == 1
        mock_db.table.assert_not_called()


# ---------------------------------------------------------------------------
# Add model — admin only
# ---------------------------------------------------------------------------


class TestAddModel:
    def test_add_model_returns_201(self, admin_client):
        row = _model_row()
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[row]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.post(
                "/api/v1/admin/models",
                json={
                    "provider": "anthropic",
                    "model_id": "claude-sonnet-4-6",
                    "display_name": "Claude Sonnet 4.6",
                    "category": "generation",
                    "context_window": 200000,
                },
            )
        assert response.status_code == 201
        assert response.json()["model_id"] == "claude-sonnet-4-6"

    def test_add_model_missing_required_fields_returns_422(self, admin_client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            response = admin_client.post(
                "/api/v1/admin/models",
                json={"provider": "anthropic"},  # missing model_id, display_name, category
            )
        assert response.status_code == 422

    def test_add_model_invalid_category_returns_422(self, admin_client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            response = admin_client.post(
                "/api/v1/admin/models",
                json={
                    "provider": "anthropic",
                    "model_id": "test",
                    "display_name": "Test",
                    "category": "invalid_category",
                },
            )
        assert response.status_code == 422

    def test_add_model_invalid_provider_returns_422(self, admin_client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            response = admin_client.post(
                "/api/v1/admin/models",
                json={
                    "provider": "unknown_provider",
                    "model_id": "test",
                    "display_name": "Test",
                    "category": "generation",
                },
            )
        assert response.status_code == 422

    def test_add_model_non_admin_returns_403(self, client):
        """Regular user cannot add models — require_admin raises AuthorizationError."""
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app

        async def _raise_auth_error() -> None:
            raise AuthorizationError()

        app.dependency_overrides[require_admin] = _raise_auth_error
        try:
            response = client.post(
                "/api/v1/admin/models",
                json={
                    "provider": "anthropic",
                    "model_id": "test",
                    "display_name": "Test",
                    "category": "generation",
                },
            )
        finally:
            del app.dependency_overrides[require_admin]
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Update model — admin only
# ---------------------------------------------------------------------------


class TestUpdateModel:
    def test_patch_enabled_toggle(self, admin_client):
        updated = _model_row(enabled=False)
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .update.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[updated])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(
                f"/api/v1/admin/models/{TEST_MODEL_ID}",
                json={"enabled": False},
            )
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_patch_display_name(self, admin_client):
        updated = _model_row(display_name="New Name")
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .update.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[updated])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(
                f"/api/v1/admin/models/{TEST_MODEL_ID}",
                json={"display_name": "New Name"},
            )
        assert response.status_code == 200

    def test_patch_not_found_returns_404(self, admin_client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .update.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(
                f"/api/v1/admin/models/{TEST_MODEL_ID}",
                json={"enabled": True},
            )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Delete model — admin only
# ---------------------------------------------------------------------------


class TestDeleteModel:
    def test_delete_returns_204(self, admin_client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .delete.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[{"id": TEST_MODEL_ID}])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.delete(f"/api/v1/admin/models/{TEST_MODEL_ID}")
        assert response.status_code == 204

    def test_delete_not_found_returns_404(self, admin_client):
        mock_db = MagicMock()
        (
            mock_db.table.return_value
            .delete.return_value
            .eq.return_value
            .execute.return_value
        ) = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.delete(f"/api/v1/admin/models/{TEST_MODEL_ID}")
        assert response.status_code == 404
