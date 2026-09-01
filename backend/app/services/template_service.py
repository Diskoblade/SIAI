"""DocumentTemplateService — company letterhead (Approval Note master template).

Uploading a new letterhead marks the previous active one inactive and bumps the
version; the master file is never edited in place. The company scope is always
derived from the authenticated user, never from a request.
"""

from __future__ import annotations

import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.approval_note import CompanyDocumentTemplate, TemplateType
from app.models.user import User
from app.services import document_storage

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class TemplateError(Exception):
    """Base class for user-facing template errors."""


class InvalidDocxError(TemplateError):
    pass


class TemplateTooLargeError(TemplateError):
    pass


class NoActiveTemplateError(TemplateError):
    pass


def _company_id(user: User) -> int:
    # Single-tenant: derived from configuration, never from the request body.
    return settings.default_company_id


def validate_docx(filename: str, data: bytes) -> None:
    if not filename.lower().endswith(".docx"):
        raise InvalidDocxError("Only .docx files are accepted.")
    if len(data) > settings.max_docx_upload_bytes:
        raise TemplateTooLargeError(
            f"File exceeds the {settings.max_docx_upload_bytes // (1024 * 1024)} MB limit."
        )
    # DOCX is a zip starting with 'PK'; confirm python-docx can open it.
    if data[:2] != b"PK":
        raise InvalidDocxError("The file is not a valid DOCX document.")
    try:
        from docx import Document

        Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise InvalidDocxError("The file could not be read as a DOCX document.") from exc


def get_active_letterhead(db: Session, user: User) -> CompanyDocumentTemplate | None:
    return db.scalar(
        select(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.company_id == _company_id(user),
            CompanyDocumentTemplate.template_type == TemplateType.approval_note_letterhead,
            CompanyDocumentTemplate.is_active.is_(True),
        )
    )


def require_active_letterhead(db: Session, user: User) -> CompanyDocumentTemplate:
    template = get_active_letterhead(db, user)
    if template is None:
        raise NoActiveTemplateError("No active Approval Note letterhead is configured.")
    return template


def get_template_for_company(
    db: Session, user: User, template_id: int
) -> CompanyDocumentTemplate | None:
    """Company-scoped fetch — a template from another company is invisible."""
    return db.scalar(
        select(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.id == template_id,
            CompanyDocumentTemplate.company_id == _company_id(user),
        )
    )


def upload_letterhead(
    db: Session, user: User, *, filename: str, data: bytes, name: str | None = None
) -> CompanyDocumentTemplate:
    """Upload/replace the active letterhead. Previous active version is retired."""
    validate_docx(filename, data)
    company_id = _company_id(user)

    previous = get_active_letterhead(db, user)
    next_version = (previous.version + 1) if previous else 1
    if previous is not None:
        previous.is_active = False  # retain history; only deactivate

    storage_key = document_storage.save_bytes("templates", data)
    template = CompanyDocumentTemplate(
        company_id=company_id,
        template_type=TemplateType.approval_note_letterhead,
        name=name or (filename.rsplit(".", 1)[0]),
        original_filename=filename,
        storage_key=storage_key,
        mime_type=DOCX_MIME,
        file_size=len(data),
        version=next_version,
        is_active=True,
        created_by=user.id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def read_template_bytes(template: CompanyDocumentTemplate) -> bytes:
    return document_storage.read_bytes("templates", template.storage_key)
