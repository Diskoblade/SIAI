"""Authentication routes: signup, login, me, logout."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser
from app.core.security import create_access_token
from app.database import get_db
from app.models.user import UserStatus
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    SignupRequest,
    SignupResponse,
    TokenResponse,
)
from app.schemas.user import UserMe
from app.services import auth_service
from app.services.authorization_service import resolve_allowed_scopes
from app.services.serializers import to_user_me, to_user_public

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]

# Shown to the user on login for non-approved statuses. Kept in one place.
_LOGIN_STATUS_MESSAGE = {
    UserStatus.pending: "Your account is awaiting administrator approval.",
    UserStatus.rejected: "Your account has not been approved.",
    UserStatus.disabled: "Your account is disabled. Contact the administrator.",
}


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: DbSession) -> SignupResponse:
    """Register a new account as pending. Never issues a token."""
    try:
        user = auth_service.create_user(db, payload)
    except auth_service.EmailAlreadyRegisteredError:
        # Duplicate email is a legitimate, non-sensitive validation message.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )
    except auth_service.InvalidDepartmentError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid department.",
        )
    except Exception:  # noqa: BLE001 - never leak internal errors to the client
        logger.exception("Unexpected error during signup")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create account. Please try again later.",
        )

    return SignupResponse(
        id=user.id,
        email=user.email,
        status=user.status.value,
        message=(
            "Account created successfully. "
            "Your account is waiting for administrator approval."
        ),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    """Verify credentials and status, then issue a JWT for approved accounts."""
    user = auth_service.authenticate_user(db, payload.email, payload.password)

    # Generic message — never reveals whether the email exists.
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if user.status is not UserStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_LOGIN_STATUS_MESSAGE.get(user.status, "Account not permitted."),
        )

    token = create_access_token(
        subject=user.id,
        department_id=user.department_id,
        role=user.role.value,
    )
    return TokenResponse(access_token=token, token_type="bearer", user=to_user_public(user))


@router.get("/me", response_model=UserMe)
def read_me(current_user: CurrentUser, db: DbSession) -> UserMe:
    """Return the authenticated user's safe profile and resolved data scopes."""
    me = to_user_me(current_user)
    me.allowed_scopes = resolve_allowed_scopes(db, current_user)
    return me


@router.post("/logout", response_model=MessageResponse)
def logout(current_user: CurrentUser) -> MessageResponse:
    """Stateless logout.

    JWTs are stateless, so the client discards the token. This endpoint exists
    for a clean client contract and future extension (e.g. token denylist).
    """
    return MessageResponse(message="Logged out.")
