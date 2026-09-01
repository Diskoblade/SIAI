"""Admin schemas for managing users."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.user import UserRole, UserStatus


class AdminUserUpdate(BaseModel):
    """Partial update applied by an administrator.

    Every field is optional; only the provided fields are changed. This is the
    ONLY sanctioned path for changing a user's department, role, or status.
    """

    model_config = ConfigDict(extra="forbid")

    status: UserStatus | None = None
    role: UserRole | None = None
    department_id: int | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "AdminUserUpdate":
        if self.status is None and self.role is None and self.department_id is None:
            raise ValueError("At least one of status, role, or department_id is required.")
        return self
