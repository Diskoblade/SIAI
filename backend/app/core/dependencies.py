"""Reusable FastAPI security dependencies.

`get_current_user` is the single choke point for authentication. It always
reloads the user (and their role/status/department) from the database, so a
stale JWT cannot grant access after an admin disables the account or changes
its permissions.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_access_token
from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.services import auth_service

# auto_error=False lets us return our own consistent 401 for a missing token.
_bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)

# Human-readable reasons for why an authenticated (but not approved) account
# is blocked from protected resources.
_STATUS_BLOCK_MESSAGE = {
    UserStatus.pending: "Your account is awaiting administrator approval.",
    UserStatus.rejected: "Your account has not been approved.",
    UserStatus.disabled: "Your account is disabled. Contact the administrator.",
}


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Authenticate the request and return the *current* database user.

    Enforces, in order: token present -> signature/expiry valid -> subject is a
    real user id -> user still exists -> user status is approved.
    """
    if credentials is None or not credentials.credentials:
        raise _UNAUTHENTICATED

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    subject = payload.get("sub")
    if subject is None:
        raise _UNAUTHENTICATED
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise _UNAUTHENTICATED

    # Authorization data (role/status/department) comes from the DB, never the
    # token — this is what makes a revoked/downgraded account take effect.
    user = auth_service.get_user_by_id(db, user_id)
    if user is None:
        raise _UNAUTHENTICATED

    if user.status is not UserStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_STATUS_BLOCK_MESSAGE.get(user.status, "Account not permitted."),
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(current_user: CurrentUser) -> User:
    """Dependency that allows only approved administrators."""
    if current_user.role is not UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges are required.",
        )
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]
