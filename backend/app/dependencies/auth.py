from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import decode_token, lookup_api_key
from app.utils.errors import ForbiddenError, UnauthorizedError


class CurrentUser:
    """Extracted from a valid JWT token or API key."""

    def __init__(
        self,
        user_id: str,
        email: str,
        name: str,
        org_id: str,
        role: str,
        api_key_id: str | None = None,
    ):
        self.user_id = user_id
        self.email = email
        self.name = name
        self.org_id = org_id
        self.role = role
        self.api_key_id = api_key_id  # set when authenticated via API key


async def get_current_user(request: Request) -> CurrentUser:
    """FastAPI dependency — extracts user from JWT Bearer token only."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid Authorization header")

    token = auth_header.split(" ", 1)[1]

    # If it looks like an API key (starts with sk-), reject — use get_current_user_or_api_key instead
    if token.startswith("sk-"):
        raise UnauthorizedError("API keys not accepted on this endpoint. Use JWT.")

    payload = decode_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid token payload")

    return CurrentUser(
        user_id=user_id,
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        org_id=payload.get("org_id", ""),
        role=payload.get("role", "viewer"),
    )


async def get_current_user_or_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """
    FastAPI dependency — try JWT first, then API key.
    Used on inference endpoints that accept both auth methods.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid Authorization header")

    token = auth_header.split(" ", 1)[1]

    # ── API key path ──
    if token.startswith("sk-"):
        api_key = await lookup_api_key(db, token)
        if not api_key:
            raise UnauthorizedError("Invalid or revoked API key")

        return CurrentUser(
            user_id=str(api_key.created_by_user_id),
            email="",
            name="api-key",
            org_id=str(api_key.org_id),
            role="operator",  # API keys get operator-level access
            api_key_id=str(api_key.id),
        )

    # ── JWT path ──
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid token payload")

    return CurrentUser(
        user_id=user_id,
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        org_id=payload.get("org_id", ""),
        role=payload.get("role", "viewer"),
    )


def require_role(*allowed_roles: str) -> Callable:
    """
    Dependency factory — restricts access to users with one of the allowed roles.

    Usage:
        @router.get("/admin/orgs", dependencies=[Depends(require_role("platform_admin"))])
    """

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise ForbiddenError(
                f"This action requires one of these roles: {', '.join(allowed_roles)}"
            )
        return user

    return _check
