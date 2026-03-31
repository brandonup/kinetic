"""
Security Tests — KIN-349

Focused security test coverage across all attack surfaces:
  - Admin route enforcement (non-admin → 403)
  - Cross-user ownership isolation (conversations, companies)
  - BYOK key never exposed in responses (already covered in test_profile.py — verified here at integration level)
  - MCP token revocation + access control (covered in test_mcp.py — additional cross-cutting tests here)

Run with:  python -m pytest tests/test_security.py -v
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID, TEST_ADMIN_ID

# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

_ADMIN_MODELS_DB = "app.api.routes.admin_models.get_supabase_client"
_ADMIN_USERS_DB = "app.api.routes.admin_users.get_supabase_client"
_CONVERSATIONS_DB = "app.api.routes.conversations.get_supabase_client"
_COMPANIES_DB = "app.api.routes.companies.get_supabase_client"
_PROFILE_DB = "app.api.routes.profile.get_supabase_client"


# ---------------------------------------------------------------------------
# Admin Route Enforcement — non-admin gets 403
# Tests for admin endpoints missing explicit 403 coverage.
# ---------------------------------------------------------------------------


def _override_require_admin_to_raise():
    """Override require_admin to raise AuthorizationError (simulates non-admin user)."""
    from app.auth.deps import require_admin
    from app.core.errors import AuthorizationError
    from app.main import app

    async def _raise():
        raise AuthorizationError()

    app.dependency_overrides[require_admin] = _raise
    return require_admin


def _clear_override(dep):
    from app.main import app
    app.dependency_overrides.pop(dep, None)


class TestAdminModelsEnforcement:
    """PATCH and DELETE /admin/models require admin — non-admin gets 403."""

    def test_update_model_non_admin_returns_403(self, client):
        dep = _override_require_admin_to_raise()
        try:
            resp = client.patch(
                f"/api/v1/admin/models/{uuid4()}",
                json={"display_name": "test"},
            )
            assert resp.status_code == 403
        finally:
            _clear_override(dep)

    def test_delete_model_non_admin_returns_403(self, client):
        dep = _override_require_admin_to_raise()
        try:
            resp = client.delete(f"/api/v1/admin/models/{uuid4()}")
            assert resp.status_code == 403
        finally:
            _clear_override(dep)


class TestAdminUsersEnforcement:
    """PATCH /admin/users/{id}/enable requires admin — non-admin gets 403."""

    def test_enable_user_non_admin_returns_403(self, client):
        dep = _override_require_admin_to_raise()
        try:
            resp = client.patch(f"/api/v1/admin/users/{uuid4()}/enable")
            assert resp.status_code == 403
        finally:
            _clear_override(dep)


# ---------------------------------------------------------------------------
# Conversation Ownership Enforcement
# store_message filters by user_id — another user's conversation returns 404.
# ---------------------------------------------------------------------------


class TestConversationOwnership:
    """Conversation endpoints enforce user ownership — no cross-user access."""

    def test_store_message_in_other_users_conversation_returns_404(self, client):
        """Conversation exists but belongs to another user → 404 (anti-enumeration)."""
        other_conv_id = str(uuid4())

        def _table(name):
            chain = MagicMock()
            if name == "conversations":
                # Query filters by user_id — returns None for non-owner
                chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data=None
                )
            return chain

        db = MagicMock()
        db.table.side_effect = _table
        with patch(_CONVERSATIONS_DB, return_value=db):
            resp = client.post(
                f"/api/v1/conversations/{other_conv_id}/messages",
                json={"role": "user", "content": "I shouldn't be here."},
            )
        assert resp.status_code == 404

    def test_store_message_soft_deleted_conversation_returns_404(self, client):
        """Soft-deleted conversation → 404 (is_("deleted_at", "null") filter)."""
        deleted_conv_id = str(uuid4())

        def _table(name):
            chain = MagicMock()
            if name == "conversations":
                # Soft-deleted conversation: is_("deleted_at", "null") filter excludes it
                chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data=None
                )
            return chain

        db = MagicMock()
        db.table.side_effect = _table
        with patch(_CONVERSATIONS_DB, return_value=db):
            resp = client.post(
                f"/api/v1/conversations/{deleted_conv_id}/messages",
                json={"role": "user", "content": "conversation was deleted"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Company Ownership Enforcement
# GET/PATCH/DELETE companies filter by user_id.
# ---------------------------------------------------------------------------


class TestCompanyOwnership:
    """Company endpoints enforce user ownership — no cross-user access."""

    def test_get_company_not_owned_returns_404(self, client):
        """GET /companies/{id} where company belongs to another user → 404."""
        other_company_id = str(uuid4())
        db = MagicMock()
        # select().eq("id", ...).eq("user_id", ...) returns None for non-owner
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        with patch(_COMPANIES_DB, return_value=db):
            resp = client.get(f"/api/v1/companies/{other_company_id}")
        assert resp.status_code == 404

    def test_patch_company_not_owned_returns_404(self, client):
        """PATCH /companies/{id} where company belongs to another user → 404."""
        # Route: .update(updates).eq("id", ...).eq("user_id", ...).execute() → empty data
        other_company_id = str(uuid4())
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        with patch(_COMPANIES_DB, return_value=db):
            resp = client.patch(
                f"/api/v1/companies/{other_company_id}",
                json={"name": "Hijacked Corp"},
            )
        assert resp.status_code == 404

    def test_delete_company_not_owned_returns_404(self, client):
        """DELETE /companies/{id} where company belongs to another user → 404."""
        # Route: .delete().eq("id", ...).eq("user_id", ...).execute() → empty data
        other_company_id = str(uuid4())
        db = MagicMock()
        db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        with patch(_COMPANIES_DB, return_value=db):
            resp = client.delete(f"/api/v1/companies/{other_company_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# BYOK Key Never Exposed — Integration-Level Verification
# ---------------------------------------------------------------------------


class TestBYOKKeyNeverExposed:
    """API keys never appear in any response — verified at the field level."""

    def test_list_api_keys_excludes_ciphertext_and_nonce(self, client):
        """GET /profile/api-keys returns provider + key_hint only, never ciphertext."""
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {"provider": "anthropic", "key_hint": "sk-...xyz", "validated_at": None},
                {"provider": "openai", "key_hint": "sk-...abc", "validated_at": None},
            ]
        )
        with patch(_PROFILE_DB, return_value=db):
            resp = client.get("/api/v1/profile/api-keys")
        assert resp.status_code == 200
        # list_api_keys returns a list directly, not {"keys": [...]}
        for key in resp.json():
            assert "key_ciphertext" not in key
            assert "key_nonce" not in key
            assert "api_key" not in key

    def test_get_profile_excludes_sensitive_fields(self, client):
        """GET /profile returns only id, name, bio, default_model_id."""
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": TEST_USER_ID, "name": "Alice", "email": "alice@example.com", "bio": "Builder", "default_model_id": None}
        )
        with patch(_PROFILE_DB, return_value=db):
            resp = client.get("/api/v1/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert "key_ciphertext" not in data
        assert "key_nonce" not in data
        assert "password" not in data


# ---------------------------------------------------------------------------
# Admin-Only Endpoint Completeness — all admin routes reject non-admin
# ---------------------------------------------------------------------------


class TestAdminRouteCompleteness:
    """Every admin endpoint (except GET /admin/models which is intentionally open)
    returns 403 for non-admin users."""

    @pytest.fixture(autouse=True)
    def _setup_non_admin(self):
        dep = _override_require_admin_to_raise()
        yield
        _clear_override(dep)

    def test_get_admin_users_non_admin_403(self, client):
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 403

    def test_disable_user_non_admin_403(self, client):
        resp = client.patch(f"/api/v1/admin/users/{uuid4()}/disable")
        assert resp.status_code == 403

    def test_enable_user_non_admin_403(self, client):
        resp = client.patch(f"/api/v1/admin/users/{uuid4()}/enable")
        assert resp.status_code == 403

    def test_transfer_agent_non_admin_403(self, client):
        resp = client.patch(f"/api/v1/admin/users/{uuid4()}/transfer-agent")
        assert resp.status_code == 403

    def test_add_model_non_admin_403(self, client):
        resp = client.post("/api/v1/admin/models", json={"provider": "test", "model_id": "x"})
        assert resp.status_code == 403

    def test_update_model_non_admin_403(self, client):
        resp = client.patch(f"/api/v1/admin/models/{uuid4()}", json={"display_name": "x"})
        assert resp.status_code == 403

    def test_delete_model_non_admin_403(self, client):
        resp = client.delete(f"/api/v1/admin/models/{uuid4()}")
        assert resp.status_code == 403

    def test_get_rag_debug_non_admin_403(self, client):
        resp = client.get("/api/v1/admin/rag-debug")
        assert resp.status_code == 403

    def test_get_rag_debug_detail_non_admin_403(self, client):
        resp = client.get(f"/api/v1/admin/rag-debug/{uuid4()}")
        assert resp.status_code == 403
