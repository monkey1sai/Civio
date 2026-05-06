"""FastAPI dependencies for authentication and authorisation.

``get_current_user`` decodes the access token, loads the ``User`` row, and
enforces ``auth_status = verified``. ``require_role`` is a factory that returns
a dependency gating the endpoint to the given roles; ``get_current_community_id``
is a convenience extractor used by tenant-scoped queries.

Routers depend on these; services should take a ``User`` argument instead of
resolving one themselves.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import AuthenticationError, AuthorizationError
from src.core.security import decode_token
from src.models.enums import AuthStatus, UserRole
from src.models.user import User
from src.repositories.user_repo import UserRepository

# ``auto_error=False`` lets us raise ``AuthenticationError`` ourselves, which
# flows through the civio exception handler and produces the standard
# ``{code, message, details}`` body instead of FastAPI's default shape.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("missing or malformed bearer token")

    payload = decode_token(credentials.credentials)
    if payload.type != "access":
        # Refresh tokens must only reach ``POST /auth/refresh``.
        raise AuthenticationError("refresh token cannot authorise requests")

    try:
        user_id = UUID(payload.sub)
    except ValueError as exc:
        raise AuthenticationError("invalid token subject") from exc

    user = await UserRepository(db).get(user_id)
    if user is None:
        raise AuthenticationError("user not found")

    if user.auth_status != AuthStatus.VERIFIED:
        raise AuthenticationError(
            "user is not verified",
            details={"auth_status": user.auth_status.value},
        )

    return user


def require_role(*roles: UserRole) -> Callable[..., Coroutine[Any, Any, User]]:
    """Return a dependency that allows only users whose role is in ``roles``."""
    allowed = frozenset(roles)

    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise AuthorizationError(
                "role not permitted for this endpoint",
                details={
                    "required": sorted(r.value for r in allowed),
                    "actual": user.role.value,
                },
            )
        return user

    return _dep


async def get_current_community_id(user: User = Depends(get_current_user)) -> UUID:
    return user.community_id
