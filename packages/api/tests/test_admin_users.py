"""Route tests for Admin User management — KIN-278 (KIN-264)."""
from __future__ import annotations

import pytest

from tests.conftest import TEST_ADMIN_ID, TEST_USER_ID, ok, empty, seq

OTHER_USER_ID = "00000000-0000-0000-0000-000000000050"

USER_ROW = {
    "id": OTHER_USER_ID,
    "name": "Other User",
    "email": "other@example.com",
    "role": "user",
    "disabled_at": None,
    "created_at": "2026-01-01T00:00:00Z",
}

DISABLED_ROW = {**USER_ROW, "disabled_at": "2026-03-23T00:00:00Z"}


class TestListUsers:
    def test_requires_admin(self, client, sb):
        """Regular user should get 403."""
        r = client.get("/api/v1/admin/users")
        assert r.status_code == 403

    def test_admin_can_list(self, admin_client, sb):
        sb.execute.return_value = ok([USER_ROW])
        r = admin_client.get("/api/v1/admin/users")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_returns_empty_list(self, admin_client, sb):
        sb.execute.return_value = ok([])
        r = admin_client.get("/api/v1/admin/users")
        assert r.status_code == 200
        assert r.json() == []


class TestGetUser:
    def test_requires_admin(self, client, sb):
        r = client.get(f"/api/v1/admin/users/{OTHER_USER_ID}")
        assert r.status_code == 403

    def test_admin_gets_user(self, admin_client, sb):
        sb.execute.return_value = ok(USER_ROW)
        r = admin_client.get(f"/api/v1/admin/users/{OTHER_USER_ID}")
        assert r.status_code == 200
        assert r.json()["id"] == OTHER_USER_ID

    def test_not_found(self, admin_client, sb):
        sb.execute.return_value = empty()
        r = admin_client.get(f"/api/v1/admin/users/{OTHER_USER_ID}")
        assert r.status_code == 404


class TestDisableUser:
    def test_cannot_disable_self(self, admin_client, sb):
        """Admin cannot disable their own account."""
        r = admin_client.patch(
            f"/api/v1/admin/users/{TEST_ADMIN_ID}/disable",
            json={"disabled": True},
        )
        assert r.status_code == 403

    def test_disable_success(self, admin_client, sb):
        seq(sb, ok(USER_ROW), ok([DISABLED_ROW]))
        r = admin_client.patch(
            f"/api/v1/admin/users/{OTHER_USER_ID}/disable",
            json={"disabled": True},
        )
        assert r.status_code == 200
        assert r.json()["disabled_at"] is not None

    def test_enable_success(self, admin_client, sb):
        seq(sb, ok(DISABLED_ROW), ok([USER_ROW]))
        r = admin_client.patch(
            f"/api/v1/admin/users/{OTHER_USER_ID}/disable",
            json={"disabled": False},
        )
        assert r.status_code == 200
        assert r.json()["disabled_at"] is None

    def test_user_not_found(self, admin_client, sb):
        seq(sb, empty())
        r = admin_client.patch(
            f"/api/v1/admin/users/{OTHER_USER_ID}/disable",
            json={"disabled": True},
        )
        assert r.status_code == 404

    def test_requires_admin(self, client, sb):
        r = client.patch(
            f"/api/v1/admin/users/{OTHER_USER_ID}/disable",
            json={"disabled": True},
        )
        assert r.status_code == 403
