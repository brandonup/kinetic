"""
Pytest configuration and shared fixtures — Kinetic API tests.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Environment stubs (must be set before app import)
# ---------------------------------------------------------------------------

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault(
    "API_KEY_ENCRYPTION_KEY",
    # 32-byte key, base64-encoded — test-only value
    "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcy10ZXN0",
)

TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """
    FastAPI TestClient with authentication bypassed.

    get_current_user is overridden to inject TEST_USER_ID without JWT validation.
    get_supabase_client is NOT overridden here — individual tests patch it.
    """
    from app.auth import CurrentUser, get_current_user
    from app.main import app

    async def _mock_auth() -> CurrentUser:
        return CurrentUser(user_id=TEST_USER_ID)

    app.dependency_overrides[get_current_user] = _mock_auth

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()
