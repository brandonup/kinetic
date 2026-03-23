"""
Auth test suite — KIN-252

Auth pattern:
  - Supabase Auth owns auth.users (magic link + Google OAuth)
  - handle_new_user() trigger fires on auth.users INSERT →
    inserts into public.users with role='user' (default)
  - JWT sub claim = public.users.id
  - require_admin() dependency checks public.users.role = 'admin'

Test tiers:
  - Unit (default): TestMagicLink, TestSession, TestRoleEnforcement
    Use dependency_overrides or raw_client with real JWT verification.
  - Integration (opt-in): TestRegistration, TestOAuth
    Require KINETIC_RUN_INTEGRATION_TESTS=1 and a live Supabase instance.

Schema ref: docs/db-schema-spec.md §1 (users table)
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import TEST_ADMIN_ID, TEST_USER_ID, skip_integration


# ---------------------------------------------------------------------------
# Registration — integration-tier (requires live Supabase + handle_new_user trigger)
# ---------------------------------------------------------------------------


class TestRegistration:
    @skip_integration
    def test_email_registration_creates_user(self, client, db_session):
        """
        When a new email is registered via magic link, the handle_new_user() trigger
        on auth.users INSERT must create a row in public.users.

        Verify by querying public.users for a row with id matching the Supabase
        auth.users UUID. Name is seeded from raw_user_meta_data->>'name' or email fallback.

        Expected:
          - public.users row exists with correct id
          - users.role = 'user' (default from handle_new_user)
          - users.name is non-null
        """
        # Integration: call Supabase Auth API to create user, then query public.users.
        # Requires real DB with handle_new_user trigger installed.
        raise NotImplementedError("Implement with live Supabase client in integration run")

    @skip_integration
    def test_duplicate_email_registration_returns_error_not_crash(self, client):
        """
        Sending a magic link to an existing Supabase email should return a handled
        4xx — not 500. Supabase Auth returns 400 on duplicate email; the app
        must surface this cleanly without a server error.

        Expected:
          - HTTP 400 (or appropriate 4xx)
          - Structured error body (not stack trace)
          - No duplicate row in public.users
        """
        raise NotImplementedError("Implement with live Supabase client in integration run")

    @skip_integration
    def test_registration_assigns_user_role_by_default(self, client, db_session):
        """
        handle_new_user() trigger must INSERT with role = 'user'.
        No path in registration should create an 'admin' role user.

        Expected:
          - public.users.role = 'user' for any newly registered user
          - Not 'admin' even for the first user registered
        """
        raise NotImplementedError("Implement with live Supabase client in integration run")

    @skip_integration
    def test_invalid_email_format_rejected(self, client):
        """
        Sending a magic link to a malformed email address (e.g., 'notanemail')
        must be rejected by Supabase Auth before any DB row is created.
        Kinetic should surface this as a structured error — not a 500.

        Expected:
          - HTTP 400 or 422
          - No public.users row created
          - Structured error body (not stack trace)
        """
        raise NotImplementedError("Implement with live Supabase client in integration run")


# ---------------------------------------------------------------------------
# Magic link — JWT validation (unit-tier, no DB needed)
# ---------------------------------------------------------------------------


class TestMagicLink:
    def test_valid_magic_link_authenticates_and_creates_session(self, client):
        """
        GET /api/v1/users/me with a valid Bearer token must return 200.
        client fixture overrides get_current_user, simulating a valid session.

        Expected:
          - HTTP 200
          - Response body contains {"id": TEST_USER_ID}
        """
        response = client.get("/api/v1/users/me")
        assert response.status_code == 200
        assert response.json()["id"] == TEST_USER_ID

    def test_expired_magic_link_is_rejected(self, raw_client, expired_token):
        """
        GET /api/v1/users/me with an expired JWT must return 401.
        SupabaseJWTVerifier raises AuthenticationError('Token has expired').

        Expected:
          - HTTP 401
          - Error body indicates token expiry (not a generic 500)
        """
        response = raw_client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "AUTHENTICATION_ERROR"

    def test_invalid_tampered_magic_link_is_rejected(self, raw_client, tampered_token):
        """
        A JWT with a corrupted signature must be rejected by SupabaseJWTVerifier.

        Expected:
          - HTTP 401
          - Structured error body, no stack trace
        """
        response = raw_client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        assert response.status_code == 401
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "AUTHENTICATION_ERROR"


# ---------------------------------------------------------------------------
# OAuth (Google) — integration-tier (requires live Supabase)
# ---------------------------------------------------------------------------


class TestOAuth:
    @skip_integration
    def test_oauth_callback_creates_or_finds_user_and_creates_session(self, client, db_session):
        """
        GET /auth/callback?code=<valid>&state=<valid> with a valid Google
        OAuth code. Supabase exchanges code → tokens; handle_new_user() fires if
        first-time user; returns access_token.

        Expected:
          - public.users row exists with email matching OAuth account
          - Session access_token returned
          - users.role = 'user' (new) or unchanged (returning user)
        """
        raise NotImplementedError("Implement with live Supabase OAuth flow in integration run")

    @skip_integration
    def test_oauth_callback_with_invalid_state_is_rejected(self, client):
        """
        GET /auth/callback with a mismatched or missing `state` param
        must be rejected (CSRF protection).

        Expected:
          - HTTP 400 or 403
          - No session created
          - No new row in public.users
        """
        raise NotImplementedError("Implement with live Supabase OAuth flow in integration run")


# ---------------------------------------------------------------------------
# Session management — unit-tier
# ---------------------------------------------------------------------------


class TestSession:
    def test_protected_route_rejects_unauthenticated_request(self, raw_client):
        """
        GET /api/v1/users/me without Authorization header.
        get_current_user() raises AuthenticationError('Missing authorization header').

        Expected:
          - HTTP 401
          - Structured error body: { error: { code, message } }
        """
        response = raw_client.get("/api/v1/users/me")
        assert response.status_code == 401
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "AUTHENTICATION_ERROR"
        assert "authorization" in body["error"]["message"].lower()

    def test_malformed_authorization_header_is_rejected(self, raw_client):
        """
        GET /api/v1/users/me with a malformed Authorization header
        (not 'Bearer <token>' format — missing 'Bearer' prefix).
        get_current_user() raises AuthenticationError('Invalid authorization header format').

        Expected:
          - HTTP 401
          - Error code: AUTHENTICATION_ERROR
        """
        response = raw_client.get(
            "/api/v1/users/me",
            headers={"Authorization": "notavalidformat"},
        )
        assert response.status_code == 401
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "AUTHENTICATION_ERROR"

    def test_protected_route_accepts_valid_jwt(self, client):
        """
        GET /api/v1/users/me with valid Bearer token (overridden via client fixture).

        Expected:
          - HTTP 200
          - Response body contains id matching TEST_USER_ID
        """
        response = client.get("/api/v1/users/me")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == TEST_USER_ID


# ---------------------------------------------------------------------------
# Role enforcement — unit-tier
# ---------------------------------------------------------------------------


class TestRoleEnforcement:
    def test_admin_endpoint_rejects_user_role(self, client):
        """
        GET /api/v1/users/admin/list with valid JWT for a user whose
        public.users.role = 'user'. require_admin() checks users.role;
        raises AuthorizationError('Admin access required').

        Supabase admin client is mocked to return role='user' (not admin),
        so require_admin raises AuthorizationError → HTTP 403.

        Expected:
          - HTTP 403
          - Error code: AUTHORIZATION_ERROR
        """
        mock_result = MagicMock()
        mock_result.data = {"role": "user"}

        with patch("app.auth.deps.supabase_admin_client") as mock_client:
            mock_client.return_value.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_result
            response = client.get("/api/v1/users/admin/list")

        assert response.status_code == 403
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "AUTHORIZATION_ERROR"

    def test_admin_endpoint_accepts_admin_role(self, admin_client):
        """
        GET /api/v1/users/admin/list with valid JWT for an admin user.
        admin_client fixture overrides require_admin → passes without DB call.

        Expected:
          - HTTP 200
          - Response body is a user list (stub: {"users": [], "admin_id": TEST_ADMIN_ID})
        """
        response = admin_client.get("/api/v1/users/admin/list")
        assert response.status_code == 200
        body = response.json()
        assert "users" in body
        assert body["admin_id"] == TEST_ADMIN_ID
