"""
Shared test fixtures for Kinetic API tests.

Auth is handled by overriding FastAPI dependencies:
  - get_current_user  → returns a regular test user
  - require_admin     → returns an admin test user

Each fixture that needs a different identity injects its own override.
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_current_user, require_admin

# ---------------------------------------------------------------------------
# Canonical test identities
# ---------------------------------------------------------------------------

REGULAR_USER_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000001"))
ADMIN_USER_ID   = str(uuid.UUID("00000000-0000-0000-0000-000000000002"))
OTHER_USER_ID   = str(uuid.UUID("00000000-0000-0000-0000-000000000003"))

REGULAR_USER = {
    "id": REGULAR_USER_ID,
    "email": "user@example.com",
    "name": "Test User",
    "role": "user",
    "disabled_at": None,
}

ADMIN_USER = {
    "id": ADMIN_USER_ID,
    "email": "admin@example.com",
    "name": "Test Admin",
    "role": "admin",
    "disabled_at": None,
}

OTHER_USER = {
    "id": OTHER_USER_ID,
    "email": "other@example.com",
    "name": "Other User",
    "role": "user",
    "disabled_at": None,
}


# ---------------------------------------------------------------------------
# Client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Unauthenticated test client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client():
    """Test client authenticated as a regular user."""
    app.dependency_overrides[get_current_user] = lambda: REGULAR_USER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def admin_client():
    """Test client authenticated as an admin user."""
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    app.dependency_overrides[require_admin]     = lambda: ADMIN_USER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_admin,     None)


@pytest.fixture
def other_client():
    """Test client authenticated as a second regular user (for ownership checks)."""
    app.dependency_overrides[get_current_user] = lambda: OTHER_USER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_company(client, name="Acme", description="A test company"):
    resp = client.post("/api/v1/companies", json={"name": name, "description": description})
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_project(client, company_id, name="Alpha", instructions="Do great work."):
    resp = client.post(
        "/api/v1/projects",
        json={"name": name, "company_id": company_id, "instructions": instructions},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
