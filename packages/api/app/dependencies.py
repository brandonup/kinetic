"""
FastAPI dependency re-exports and admin-gating.

conftest.py overrides these via app.dependency_overrides so that the same
object identity is used regardless of which route module imported it.
"""
from __future__ import annotations

from fastapi import Depends

from app.auth import CurrentUser, get_current_user  # re-export
from app.core.errors import ForbiddenError


async def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Raise 403 if the authenticated user is not an admin."""
    if current_user.role != "admin":
        raise ForbiddenError("Admin access required")
    return current_user


__all__ = ["get_current_user", "require_admin", "CurrentUser"]
