"""User model plus the role and status enumerations.

Only a password *hash* is ever stored — never the plaintext password. Roles
and statuses are constrained to a fixed vocabulary so authorization checks can
rely on them.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    user = "user"
    manager = "manager"
    admin = "admin"


class UserStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    disabled = "disabled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Emails are stored lower-cased (see auth_service) and must be unique.
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Argon2id hash. NEVER the plaintext password, and never returned by any API.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True
    )

    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=False, validate_strings=True),
        default=UserRole.user,
        nullable=False,
    )
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status", native_enum=False, validate_strings=True),
        default=UserStatus.pending,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    department: Mapped["Department | None"] = relationship(back_populates="users")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} email={self.email!r} role={self.role} status={self.status}>"
