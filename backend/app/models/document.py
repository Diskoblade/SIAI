"""Document and vector-chunk models with owner-first visibility metadata."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Visibility(str, enum.Enum):
    PRIVATE = "PRIVATE"
    DEPARTMENT = "DEPARTMENT"
    COMMON = "COMMON"


class MemoryCategory(str, enum.Enum):
    CONVERSATION = "CONVERSATION"
    PROJECT_DECISION = "PROJECT_DECISION"
    USER_NOTE = "USER_NOTE"
    PREFERENCE = "PREFERENCE"
    GENERATED_ARTIFACT = "GENERATED_ARTIFACT"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(400), nullable=False)

    # The department that owns the document (resolved from the uploader's
    # permissions on the backend — never trusted from a normal user request).
    owner_department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True
    )

    # Ownership is independent of visibility and never changes when a user
    # shares or unshares the document. Legacy rows may be null until backfilled.
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # Null is reserved for pre-feature rows which retain their legacy
    # access_scope behavior. All newly ingested content sets this explicitly.
    visibility: Mapped[Visibility | None] = mapped_column(
        SAEnum(Visibility, name="document_visibility", native_enum=False),
        nullable=True,
        index=True,
    )
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document_type: Mapped[str] = mapped_column(String(80), default="document")
    classification: Mapped[str] = mapped_column(String(80), default="internal")
    memory_category: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # The authoritative authorization field. A user may retrieve a chunk only
    # if one of their allowed scopes intersects this list.
    access_scope: Mapped[list] = mapped_column(JSON, default=list)

    source_filename: Mapped[str | None] = mapped_column(String(400), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="ingested")

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Denormalized authorization metadata copied from the parent document so a
    # single chunk row is self-sufficient for filtering.
    department_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    visibility: Mapped[Visibility | None] = mapped_column(
        SAEnum(Visibility, name="chunk_visibility", native_enum=False),
        nullable=True,
        index=True,
    )
    access_scope: Mapped[list] = mapped_column(JSON, default=list)

    document_title: Mapped[str] = mapped_column(String(400), default="")
    document_type: Mapped[str] = mapped_column(String(80), default="document")
    memory_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(400), nullable=True)
    subsection: Mapped[str | None] = mapped_column(String(400), nullable=True)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Dense embedding (list[float]) and sparse token list, stored as JSON so the
    # default SQLite vector store works with no external service.
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    tokens: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    document: Mapped["Document"] = relationship(back_populates="chunks")
