"""
Shared test fixtures for the Kinetic API test suite.

Supabase is always mocked — no live DB calls in unit tests.
Patch target: app.db._supabase_client
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth import UserContext, get_current_user
from app.main import app


# ---------------------------------------------------------------------------
# Default test IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "00000000-0000-0000-0000-000000000010"
TEST_ADMIN_ID = "00000000-0000-0000-0000-000000000099"
TEST_COMPANY_ID = "00000000-0000-0000-0000-000000000020"
TEST_PROJECT_ID = "00000000-0000-0000-0000-000000000030"
TEST_AGENT_ID = "00000000-0000-0000-0000-000000000040"
TEST_MODEL_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# User factory
# ---------------------------------------------------------------------------


def make_user(**kwargs) -> UserContext:
    defaults = {
        "id": TEST_USER_ID,
        "email": "test@example.com",
        "name": "Test User",
        "role": "user",
        "disabled_at": None,
    }
    defaults.update(kwargs)
    return UserContext(**defaults)


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def ok(data: Any) -> MagicMock:
    """Supabase execute() result with data."""
    r = MagicMock()
    r.data = data
    return r


def empty() -> MagicMock:
    """Supabase execute() result with no data."""
    r = MagicMock()
    r.data = None
    return r


def seq(mock: MagicMock, *results: MagicMock) -> None:
    """Configure mock.execute() to return results in sequence."""
    mock.execute.side_effect = list(results)


# ---------------------------------------------------------------------------
# Supabase mock factory
# ---------------------------------------------------------------------------


def make_supabase_mock() -> MagicMock:
    """Return a MagicMock that mimics the Supabase client chain.

    Every chained method call returns the mock itself.
    execute() returns data=None by default; use seq() or .execute.side_effect to override.
    """
    mock = MagicMock()
    mock.table.return_value = mock
    mock.select.return_value = mock
    mock.eq.return_value = mock
    mock.neq.return_value = mock
    mock.in_.return_value = mock
    mock.is_.return_value = mock
    mock.order.return_value = mock
    mock.limit.return_value = mock
    mock.maybe_single.return_value = mock
    mock.insert.return_value = mock
    mock.update.return_value = mock
    mock.delete.return_value = mock
    mock.upsert.return_value = mock
    mock.rpc.return_value = mock
    mock.execute.return_value = empty()
    return mock


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sb():
    """Supabase mock patched into app.db._supabase_client. Alias: sb."""
    mock = make_supabase_mock()
    with patch("app.db._supabase_client", mock):
        yield mock


# Keep the old name for backwards compatibility with existing tests
@pytest.fixture
def supabase_mock(sb):
    return sb


@pytest.fixture
def current_user():
    return make_user()


@pytest.fixture
def admin_user():
    return make_user(id=TEST_ADMIN_ID, role="admin", email="admin@example.com")


@pytest.fixture
def client(sb, current_user):
    """HTTP TestClient with regular user + mocked Supabase."""
    app.dependency_overrides[get_current_user] = lambda: current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def admin_client(sb, admin_user):
    """HTTP TestClient with admin user + mocked Supabase."""
    app.dependency_overrides[get_current_user] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)
