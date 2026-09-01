"""Authentication request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.user import UserPublic


class SignupRequest(BaseModel):
    """Signup payload.

    Note: `role` and `status` are intentionally NOT accepted here — new
    accounts are always created as role=user / status=pending by the backend.
    The requested `department_id` is only a *request*; an administrator
    verifies or changes it before the account is activated.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    # Minimum length enforced here; hashing happens in the service layer.
    password: str = Field(min_length=8, max_length=128)
    department_id: int


class SignupResponse(BaseModel):
    """Safe signup response — no password data, no token (account is pending)."""

    id: int
    email: EmailStr
    status: str
    message: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """Successful login response."""

    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class MessageResponse(BaseModel):
    message: str
