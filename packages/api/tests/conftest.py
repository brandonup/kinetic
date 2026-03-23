"""
Shared test fixtures for the Kinetic API test suite.

Supabase is always mocked — no live DB calls in unit tests.
Patch target: app.db._supabase_client
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth import UserContext
from app.main import app


# ---------------------------------------------------------------------------
# Default test user
# ---------------------------------------------------------------------------

TEST_USER_ID = "user-123"
TEST_COMPANY_ID = "company-456"
TEST_PROJECT_ID = "project-789"
TEST_AGENT_ID = "agent-abc"


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
# Supabase mock factory
# ---------------------------------------------------------------------------


def make_supabase_mock() -> MagicMock:
    """Return a MagicMock that mimics the Supabase client chain.

    Chain: .table(x).select(y).eq(z).maybe_single().execute()
    The final .execute() returns a MagicMock with .data = None by default.
    """
    mock = MagicMock()
    # Default: every chained call returns the mock itself; execute() returns data=None
    _result = MagicMock()
    _result.data = None
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
    mock.execute.return_value = _result
    return mock


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def supabase_mock():
    """Supabase client mock, patched into app.db._supabase_client."""
    mock = make_supabase_mock()
    with patch("app.db._supabase_client", mock):
        yield mock


@pytest.fixture
def current_user():
    return make_user()


@pytest.fixture
def admin_user():
    return make_user(role="admin")
