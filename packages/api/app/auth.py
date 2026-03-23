"""
Authentication dependency — Kinetic API.

Reads the JWT from:
  1. Authorization: Bearer <token> header
  2. ?token=<token> query param (for EventSource / SSE compatibility)

Supabase JWTs are HS256-signed with SUPABASE_JWT_SECRET.
We decode them using stdlib hmac/hashlib to avoid cryptography package conflicts.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import UnauthorizedError

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    user_id: str


def _b64url_decode(s: str) -> bytes:
    """Decode a base64url string (no padding required)."""
    # Add padding
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _verify_hs256_jwt(token: str, secret: str) -> dict:
    """
    Verify an HS256 JWT and return the payload dict.
    Raises UnauthorizedError on any failure.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise UnauthorizedError("Malformed JWT")

    header_b64, payload_b64, sig_b64 = parts

    # Verify signature
    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(
        secret.encode(),
        signing_input,
        hashlib.sha256,
    ).digest()

    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception as exc:
        raise UnauthorizedError("Invalid JWT signature encoding") from exc

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise UnauthorizedError("JWT signature verification failed")

    # Decode payload
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:
        raise UnauthorizedError("Invalid JWT payload") from exc

    return payload


async def get_current_user(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(_bearer)
    ] = None,
    token: Annotated[Optional[str], Query()] = None,
) -> CurrentUser:
    """FastAPI dependency — returns CurrentUser or raises 401."""
    raw_token: Optional[str] = None

    if credentials is not None:
        raw_token = credentials.credentials
    elif token is not None:
        raw_token = token

    if not raw_token:
        raise UnauthorizedError("Not authenticated")

    secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    if not secret:  # pragma: no cover
        raise UnauthorizedError("JWT secret not configured")

    payload = _verify_hs256_jwt(raw_token, secret)

    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Token missing sub claim")

    return CurrentUser(user_id=user_id)


# Type alias for route signatures
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
