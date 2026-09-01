"""Per-user browser IDE workspace mapping.

The OpenHands runtime itself is provisioned by infrastructure. This table keeps
only the non-secret external workspace identity and its approved launch URL.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdeWorkspace(Base):
    __tablename__ = "ide_workspaces"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(40), default="openhands", nullable=False)
    external_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    launch_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="provisioning", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
