"""
Users API router — KIN-252.

Provides the /api/v1/users/me endpoint used by the frontend to confirm
authentication and retrieve the current user's ID.

Schema ref: docs/db-schema-spec.md §1 (users table)
"""

from fastapi import APIRouter, Depends

from app.auth.deps import CurrentUser, get_current_user, require_admin

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me")
async def get_me(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """
    Return the current authenticated user's ID.

    Returns:
        {"id": "<user_id>"}

    Raises:
        AuthenticationError (401): No valid token present.
    """
    return {"id": current_user.user_id}


@router.get("/admin/list")
async def list_users(current_user: CurrentUser = Depends(require_admin)) -> dict:
    """
    Admin-only endpoint: return a stub user list.

    Raises:
        AuthenticationError (401): No valid token.
        AuthorizationError (403): User is not an admin.
    """
    # Stub response — full implementation in a later ticket
    return {"users": [], "admin_id": current_user.user_id}
