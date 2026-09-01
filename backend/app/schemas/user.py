"""User schemas — safe representations returned by the API.

None of these ever include `password_hash`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import UserRole, UserStatus


class UserPublic(BaseModel):
    """Profile returned on login (nested under the token response)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    department_id: int | None
    department_name: str | None
    role: UserRole


class UserMe(UserPublic):
    """The `/auth/me` view — adds status and the backend-resolved data scopes."""

    status: UserStatus
    # Trusted scopes the user may retrieve from (derived server-side).
    allowed_scopes: list[str] = []


class UserAdminView(BaseModel):
    """Full user row for the admin dashboard (still no password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    department_id: int | None
    department_name: str | None
    role: UserRole
    status: UserStatus
    created_at: datetime
    updated_at: datetime
