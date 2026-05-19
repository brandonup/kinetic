"""
FastAPI authentication dependencies for Kinetic.

Auth pattern:
  - Supabase Auth owns auth.users (magic link + Google OAuth)
  - handle_new_user() DB trigger creates public.users on signup
  - JWT sub claim == public.users.id
  - require_admin() checks public.users.role = 'admin' via service-role client

No SQLAlchemy — all DB reads go through Supabase Python client.
All Supabase calls inside async functions use run_in_executor per conventions.md.

Schema ref: docs/db-schema-spec.md §1 (users table)
"""

import asyncio
import logging
from functools import lru_cache
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, Query
from supabase import Client, create_client

from app.auth.supabase_jwt import get_jwt_verifier
from app.core.config import settings
from app.core.errors import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supabase admin client
# Uses service-role key — bypasses RLS for auth checks.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def supabase_admin_client() -> Client:
    """
    Return a cached Supabase client with service-role key.

    Used exclusively for internal auth checks (role lookup) where the caller
    has already been authenticated via JWT. Never return this client to
    external callers.
    """
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


# ---------------------------------------------------------------------------
# CurrentUser container
# ---------------------------------------------------------------------------

class CurrentUser:
    """Holds the authenticated user's ID extracted from the Supabase JWT."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    def __repr__(self) -> str:
        return f"CurrentUser(user_id={self.user_id})"


# ---------------------------------------------------------------------------
# Core auth dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_debug_user_id: Optional[str] = Header(None, alias="X-Debug-User-Id"),
) -> CurrentUser:
    """
    FastAPI dependency: verify Supabase JWT from Authorization header.

    Args:
        authorization: Bearer token in Authorization header.
        x_debug_user_id: Only accepted when LOCAL_DEV_AUTH_BYPASS=True.

    Returns:
        CurrentUser with user_id from JWT sub claim.

    Raises:
        AuthenticationError: Token is missing, malformed, or invalid.
    """
    if not authorization:
        if settings.LOCAL_DEV_AUTH_BYPASS and x_debug_user_id:
            try:
                UUID(x_debug_user_id)
            except Exception as err:
                raise AuthenticationError("Invalid debug user id") from err
            return CurrentUser(user_id=x_debug_user_id)
        raise AuthenticationError("Missing authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError("Invalid authorization header format")

    token = parts[1]

    # Long-lived admin CLI token (KIN-476 follow-up).
    # Allows terminal ops to bypass the 1hr Supabase JWT TTL.
    # Activated only when both ADMIN_CLI_TOKEN and ADMIN_CLI_USER_ID are set
    # in env. The bearer token must match ADMIN_CLI_TOKEN exactly.
    if (
        settings.ADMIN_CLI_TOKEN
        and settings.ADMIN_CLI_USER_ID
        and token == settings.ADMIN_CLI_TOKEN
    ):
        try:
            UUID(settings.ADMIN_CLI_USER_ID)
        except Exception as err:
            logger.error("ADMIN_CLI_USER_ID is not a valid UUID")
            raise AuthenticationError("Invalid admin CLI configuration") from err
        logger.info("Authenticated via ADMIN_CLI_TOKEN as %s", settings.ADMIN_CLI_USER_ID)
        return CurrentUser(user_id=settings.ADMIN_CLI_USER_ID)

    try:
        user_id = get_jwt_verifier().get_user_id(token)
        logger.debug(f"Authenticated user: {user_id}")
        return CurrentUser(user_id=user_id)
    except Exception as e:
        logger.error(f"Authentication failed: {str(e)}")
        raise


async def get_current_user_from_token(
    authorization: Optional[str] = Header(None),
    access_token: Optional[str] = Query(None),
    x_debug_user_id: Optional[str] = Header(None, alias="X-Debug-User-Id"),
) -> CurrentUser:
    """
    FastAPI dependency: verify Supabase JWT from header OR query param.

    Used for SSE endpoints where EventSource cannot send custom headers.
    Header takes priority over query param.

    Raises:
        AuthenticationError: Token is missing or invalid.
    """
    token: Optional[str] = None

    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]

    if not token and access_token:
        token = access_token

    if not token:
        if settings.LOCAL_DEV_AUTH_BYPASS and x_debug_user_id:
            try:
                UUID(x_debug_user_id)
            except Exception as err:
                raise AuthenticationError("Invalid debug user id") from err
            return CurrentUser(user_id=x_debug_user_id)
        raise AuthenticationError("Missing authorization token")

    try:
        user_id = get_jwt_verifier().get_user_id(token)
        logger.debug(f"Authenticated user: {user_id}")
        return CurrentUser(user_id=user_id)
    except Exception as e:
        logger.error(f"Authentication failed: {str(e)}")
        raise


# ---------------------------------------------------------------------------
# Role / status dependencies
# ---------------------------------------------------------------------------

async def require_active_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    Require an authenticated user.

    Kinetic MVP has no account suspension — this is a passthrough to
    get_current_user. Kept for interface compatibility with future
    suspension logic.
    """
    return current_user


async def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    Require the authenticated user to have role='admin' in public.users.

    Reads role from public.users via service-role client (bypasses RLS).
    Supabase call is wrapped in run_in_executor per conventions.md.

    Schema ref: docs/db-schema-spec.md §1 — table: users, column: role

    Raises:
        AuthorizationError: User is not an admin.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: supabase_admin_client()
            .table("users")
            .select("role")
            .eq("id", current_user.user_id)
            .single()
            .execute(),
    )

    if not result.data or result.data.get("role") != "admin":
        raise AuthorizationError(
            "Admin access required",
            details={"required_role": "admin"},
        )

    return current_user


# ---------------------------------------------------------------------------
# Convenience aliases
# ---------------------------------------------------------------------------

get_current_user_dep = Depends(get_current_user)
