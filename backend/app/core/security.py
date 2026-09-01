"""Password hashing and JWT helpers.

Password hashing uses Argon2id (via argon2-cffi). JWT access tokens are signed
with HS256 using a secret loaded from the environment. The signing secret is
never logged or returned by any API.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

# A single reusable hasher. Argon2id is the default type.
_password_hasher = PasswordHasher()


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    """Return an Argon2id hash of the given plaintext password."""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return True if the plaintext matches the stored hash, else False.

    Never raises on a bad password — a mismatch or malformed hash returns
    False so callers can emit a single generic error.
    """
    try:
        return _password_hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, InvalidHashError, Exception):  # noqa: BLE001
        return False


def needs_rehash(password_hash: str) -> bool:
    """Whether an existing hash should be upgraded (parameters changed)."""
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------
class TokenError(Exception):
    """Raised when a token cannot be decoded, is expired, or is tampered with."""


def create_access_token(
    *,
    subject: str | int,
    department_id: int | None,
    role: str,
    expires_minutes: int | None = None,
) -> str:
    """Create a signed JWT access token.

    The token intentionally carries only authorization-relevant claims:
    subject (user id), department_id, and role — never passwords, hashes,
    personal documents, or secrets.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(
        minutes=expires_minutes
        if expires_minutes is not None
        else settings.jwt_access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "department_id": department_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises TokenError on any failure.

    Signature verification and expiration are both enforced by PyJWT.
    """
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        # Covers invalid signature, malformed token, wrong algorithm, etc.
        raise TokenError("Invalid token") from exc
