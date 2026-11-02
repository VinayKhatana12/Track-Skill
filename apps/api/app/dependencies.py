"""Shared FastAPI dependencies: authentication and role-based access control.

Every domain router guards its endpoints with ``require_role(*roles)`` so
authorization is enforced on the backend, never only in the UI.
"""

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_token
from app.models import User
from app.models.enums import UserRole

_bearer_scheme = HTTPBearer(auto_error=False)


def _not_authenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the caller from a Bearer access token."""
    if credentials is None:
        raise _not_authenticated()

    try:
        payload: dict[str, Any] = decode_token(credentials.credentials, expected_type="access")
    except InvalidTokenError:
        raise _not_authenticated() from None

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except ValueError:
        raise _not_authenticated() from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _not_authenticated()
    return user


def require_role(*roles: UserRole) -> Callable[..., User]:
    """Dependency factory guarding an endpoint by role.

    Called with no roles, any authenticated user passes. With roles, callers
    outside the list receive a generic 403 — the backend is the enforcement
    point, independent of what the UI hides or shows.
    """

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if roles and current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this resource.",
            )
        return current_user

    return dependency
