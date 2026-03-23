"""
Auth helpers.

CurrentUser — pydantic model populated from the validated JWT.
get_current_user — FastAPI dependency; validates the token via Supabase Auth.
Accepts JWT from Authorization: Bearer <token> header OR ?token=<jwt> query param
(EventSource cannot set custom headers, so SSE endpoints pass via query param).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Query, Request
from pydantic import BaseModel

from app.core.errors import UnauthorizedError


class UserContext(BaseModel):
    id: str
    email: Optional[str] = None
    name: str = ""
    role: str = "user"
    disabled_at: Optional[str] = None


# Alias used in route type hints
CurrentUser = UserContext


async def get_current_user(
    request: Request,
    token: Optional[str] = Query(default=None),
) -> CurrentUser:
    """Extract and validate the JWT; return a UserContext."""
    auth_header = request.headers.get("Authorization", "")
    jwt: Optional[str] = None

    if auth_header.startswith("Bearer "):
        jwt = auth_header[7:]
    elif token:
        jwt = token

    if not jwt:
        raise UnauthorizedError("No authentication token provided")

    try:
        from app.db import get_supabase_client

        supabase = get_supabase_client()
        result = supabase.auth.get_user(jwt)
        if not result or not result.user:
            raise UnauthorizedError("Invalid or expired token")

        user = result.user
        meta = user.user_metadata or {}
        return CurrentUser(
            id=str(user.id),
            email=user.email,
            name=meta.get("name", user.email or ""),
            role=meta.get("role", "user"),
            disabled_at=None,
        )
    except UnauthorizedError:
        raise
    except Exception:
        raise UnauthorizedError("Invalid or expired token")
