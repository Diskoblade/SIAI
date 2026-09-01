"""Authentication service: user lookup, signup, and credential verification.

This layer owns the rules that must never be bypassed:
  * Passwords are hashed before storage; plaintext is never persisted.
  * New accounts are always role=user / status=pending regardless of input.
  * The requested department must exist, but is treated as a *request* only.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, needs_rehash, verify_password
from app.models.department import Department
from app.models.user import User, UserRole, UserStatus
from app.schemas.auth import SignupRequest


class EmailAlreadyRegisteredError(Exception):
    """Raised when a signup email already exists."""


class InvalidDepartmentError(Exception):
    """Raised when a requested department does not exist."""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == _normalize_email(email)))


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, payload: SignupRequest) -> User:
    """Create a pending user from a signup payload.

    Raises EmailAlreadyRegisteredError or InvalidDepartmentError. The caller
    (route) translates these into safe, generic HTTP responses.
    """
    email = _normalize_email(payload.email)

    # Case-insensitive duplicate check.
    existing = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing is not None:
        raise EmailAlreadyRegisteredError()

    # The requested department must exist. It is only a request — an admin
    # verifies/changes it before the account is approved.
    department = db.get(Department, payload.department_id)
    if department is None:
        raise InvalidDepartmentError()

    user = User(
        full_name=payload.full_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        department_id=department.id,
        # Hard-coded safe defaults. Never derived from client input.
        role=UserRole.user,
        status=UserStatus.pending,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return the user if the email/password are valid, else None.

    Returning None for both "no such email" and "wrong password" lets the
    route emit a single generic message and avoids leaking which emails exist.
    A transparent hash upgrade is performed if the parameters have changed.
    """
    user = get_user_by_email(db, email)
    if user is None:
        # Still verify against a dummy hash to reduce timing differences
        # between "unknown email" and "wrong password".
        verify_password(password, _DUMMY_HASH)
        return None

    if not verify_password(password, user.password_hash):
        return None

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()

    return user


# A precomputed Argon2 hash of a random string, used only to equalize timing
# on the unknown-email path. Never matches any real password.
_DUMMY_HASH = hash_password("timing-equalization-placeholder")
