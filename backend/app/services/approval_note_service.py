"""ApprovalNoteDocumentService — create Approval Notes from the letterhead,
enforce access control, and save versioned edits.

The master letterhead is copied (never edited). Content is drafted by the
existing local LLM/RAG stack (no external AI provider).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.approval_note import ApprovalNote, ApprovalNoteStatus
from app.models.department import Department
from app.models.user import User, UserRole
from app.services import (
    approval_note_type_service,
    docx_populate,
    document_storage,
    template_service,
)


class ApprovalNoteError(Exception):
    pass


class ApprovalNoteNotFoundError(ApprovalNoteError):
    pass


class ApprovalNoteAccessError(ApprovalNoteError):
    pass


def _company_id(user: User) -> int:
    return settings.default_company_id


# --------------------------------------------------------------------------- #
# Content generation (reuses the existing local LLM; no external provider)
# --------------------------------------------------------------------------- #
def generate_content(
    note_type_name: str, title: str, parameters: dict, *, department_name: str | None = None
) -> str:
    from app.rag.reasoning import get_reasoner

    params_text = "\n".join(f"- {k}: {v}" for k, v in (parameters or {}).items())
    reasoner = get_reasoner()
    if reasoner.available:
        system = (
            "You draft concise, professional internal Approval Note content for an "
            "enterprise/government procurement context. Use clear sections and a neutral, "
            "formal tone. Do not fabricate specific confidential figures unless provided. "
            "Return plain text with short headings; no markdown symbols."
        )
        user = (
            f"Approval Note type: {note_type_name}\nTitle: {title}\n"
            f"Department: {department_name or 'N/A'}\n"
            f"Parameters:\n{params_text or '(none provided)'}\n\n"
            "Write the body: background/purpose, justification, relevant financial or "
            "technical details, and a clear recommendation for approval."
        )
        try:
            return reasoner.complete(system, user).strip()
        except Exception:  # noqa: BLE001 - fall back to a deterministic body
            pass

    lines = [f"{note_type_name}", "", "Purpose", f"This note seeks approval for: {title}.", ""]
    if params_text:
        lines += ["Details", params_text, ""]
    lines += ["Recommendation", "Approval is requested for the above."]
    return "\n".join(lines)


def _department_name(db: Session, department_id: int | None) -> str | None:
    if department_id is None:
        return None
    dept = db.get(Department, department_id)
    return dept.name if dept else None


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
def create_approval_note(
    db: Session,
    user: User,
    *,
    approval_note_type_id: int,
    parameters: dict | None = None,
    title_override: str | None = None,
) -> ApprovalNote:
    note_type = approval_note_type_service.require_selectable_type(db, user, approval_note_type_id)
    template = template_service.require_active_letterhead(db, user)  # NoActiveTemplateError

    title = (title_override or note_type.name).strip()
    department_name = _department_name(db, user.department_id)
    content = generate_content(
        note_type.name, title, parameters or {}, department_name=department_name
    )

    now = datetime.now(timezone.utc)
    number = f"AN-{now:%Y%m%d}-{document_storage.new_key()[:6].upper()}"
    extra = {
        "APPROVAL_NOTE_NUMBER": number,
        "DATE": now.strftime("%d %B %Y"),
        "DEPARTMENT": department_name or "",
        "PREPARED_BY": user.full_name,
        "COMPANY_NAME": settings.app_name,
    }

    template_bytes = template_service.read_template_bytes(template)  # StorageError if missing
    populated = docx_populate.populate_template(
        template_bytes, title=title, content=content, extra_placeholders=extra
    )
    storage_key = document_storage.save_bytes("approval_notes", populated)

    note = ApprovalNote(
        company_id=_company_id(user),
        approval_note_type_id=note_type.id,
        department_id=user.department_id,
        created_by=user.id,
        title=title,
        status=ApprovalNoteStatus.generated,
        generated_content=content,
        storage_key=storage_key,
        source_template_id=template.id,
        source_template_version=template.version,
        document_version=1,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


# --------------------------------------------------------------------------- #
# Access control
# --------------------------------------------------------------------------- #
def can_access(user: User, note: ApprovalNote) -> bool:
    if note.company_id != _company_id(user):
        return False
    if user.role is UserRole.admin:
        return True
    if user.role is UserRole.manager:
        return note.department_id == user.department_id
    return note.created_by == user.id


def get_note(db: Session, user: User, note_id: int) -> ApprovalNote:
    note = db.get(ApprovalNote, note_id)
    if note is None or note.company_id != _company_id(user):
        raise ApprovalNoteNotFoundError("Approval Note not found.")
    if not can_access(user, note):
        raise ApprovalNoteAccessError("You are not authorized to access this Approval Note.")
    return note


def list_notes(db: Session, user: User) -> list[ApprovalNote]:
    stmt = select(ApprovalNote).where(ApprovalNote.company_id == _company_id(user))
    if user.role is UserRole.manager:
        stmt = stmt.where(ApprovalNote.department_id == user.department_id)
    elif user.role is not UserRole.admin:
        stmt = stmt.where(ApprovalNote.created_by == user.id)
    stmt = stmt.order_by(ApprovalNote.created_at.desc())
    return list(db.scalars(stmt))


def read_note_bytes(note: ApprovalNote) -> bytes:
    return document_storage.read_bytes("approval_notes", note.storage_key)


# --------------------------------------------------------------------------- #
# Versioned save (used by the ONLYOFFICE callback)
# --------------------------------------------------------------------------- #
def save_new_version(db: Session, note: ApprovalNote, data: bytes, *, last_editor_id: int | None = None) -> ApprovalNote:
    """Persist an edited DOCX as a new version. The old file is only removed
    once the new one is safely stored (atomic write to a fresh key)."""
    # Sanity-check the incoming DOCX before touching anything.
    if data[:2] != b"PK":
        raise ApprovalNoteError("Received file is not a valid DOCX.")

    old_key = note.storage_key
    new_key = document_storage.save_bytes("approval_notes", data)
    note.storage_key = new_key
    note.document_version += 1
    if note.status is ApprovalNoteStatus.generated:
        note.status = ApprovalNoteStatus.editing
    db.commit()
    db.refresh(note)
    # Best-effort cleanup of the superseded file (new version already saved).
    if old_key and old_key != new_key:
        document_storage.delete("approval_notes", old_key)
    return note
