"""Approval Note models: company document templates (letterhead), configurable
Approval Note types, and the Approval Note working documents themselves.

The app is single-tenant, so `company_id` defaults to the configured company
and is always derived server-side (never from a request) — it keeps the schema
ready for multi-tenancy without changing access-control today, which is by
department + role + creator, consistent with the rest of the platform.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_company() -> int:
    return settings.default_company_id


class TemplateType(str, enum.Enum):
    approval_note_letterhead = "APPROVAL_NOTE_LETTERHEAD"


class ApprovalNoteStatus(str, enum.Enum):
    draft = "draft"
    generated = "generated"
    editing = "editing"
    finalized = "finalized"


class CompanyDocumentTemplate(Base):
    """A master document template (e.g. the Approval Note letterhead DOCX).

    The master file is stored privately by `storage_key` and is NEVER edited in
    place — Approval Notes always copy it. Replacing the letterhead marks the
    previous active template inactive and bumps the version.
    """

    __tablename__ = "company_document_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, default=_default_company, index=True)
    template_type: Mapped[TemplateType] = mapped_column(
        SAEnum(TemplateType, name="template_type", native_enum=False, validate_strings=True),
        default=TemplateType.approval_note_letterhead,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(400), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ApprovalNoteType(Base):
    """Administrator-managed Approval Note headings/categories (no hard-coding)."""

    __tablename__ = "approval_note_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, default=_default_company, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ApprovalNote(Base):
    """A working Approval Note document (a private copy of the letterhead)."""

    __tablename__ = "approval_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, default=_default_company, index=True)
    approval_note_type_id: Mapped[int] = mapped_column(
        ForeignKey("approval_note_types.id"), nullable=False
    )
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(400), nullable=False)
    status: Mapped[ApprovalNoteStatus] = mapped_column(
        SAEnum(ApprovalNoteStatus, name="approval_note_status", native_enum=False, validate_strings=True),
        default=ApprovalNoteStatus.generated,
    )
    generated_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Working DOCX file, stored privately by key (never a filesystem path).
    storage_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("company_document_templates.id"), nullable=True
    )
    source_template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_version: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def onlyoffice_key(self) -> str:
        """ONLYOFFICE document key — MUST change when the document changes."""
        return f"an-{self.id}-v{self.document_version}"
