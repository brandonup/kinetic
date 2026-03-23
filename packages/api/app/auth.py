"""
Auth helpers.

CurrentUser — pydantic model populated from the validated JWT.
get_current_user — FastAPI dependency; validates the token via Supabase Auth.
Accepts JWT from Authorization: Bearer <token> header OR ?token=<jwt> query param
(EventSource cannot set custom headers, so SSE endpoints pass via query param).
"""
from __future__ import annotations

import base64
import json
import time
from typing import Optional

from fastapi import Query, Request
from pydantic import BaseModel

from app.core.errors import UnauthorizedError


def _check_jwt_claims(jwt: str) -> None:
    """Fail-fast local check for exp/nbf claims before making a Supabase API call.

    This does NOT verify the signature — Supabase does that.  It only guards
    against obviously-expired or not-yet-valid tokens, catching the common
    case without a network round-trip.
    """
    try:
        parts = jwt.split(".")
        if len(parts) != 3:
            return  # malformed; let Supabase reject it
        # JWT payload is base64url-encoded; pad to a multiple of 4
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return  # unparseable; let Supabase reject it

    now = time.time()
    exp = payload.get("exp")
    if exp is not None and now > exp:
        raise UnauthorizedError("Token expired")
    nbf = payload.get("nbf")
    if nbf is not None and now < nbf:
        raise UnauthorizedError("Token not yet valid")


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

    _check_jwt_claims(jwt)

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
