"""Department model.

A department maps 1:1 to a VectorDB collection. The backend is the sole
authority that resolves a user's department to its `vector_collection`; the
frontend never supplies a collection name.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    # Name of the VectorDB (e.g. Qdrant) collection that holds this
    # department's documents. Resolved server-side for RAG authorization.
    vector_collection: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="department")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Department id={self.id} name={self.name!r} collection={self.vector_collection!r}>"
