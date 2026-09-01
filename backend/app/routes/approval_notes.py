"""Approval Note routes.

Admin: manage the company letterhead and Approval Note types.
User:  create / list / open / download Approval Notes they may access.

All authorization is enforced here (server-side); the frontend guards are only
for UX. Company/department scope is always derived from the authenticated user.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.dependencies import AdminUser, CurrentUser
from app.database import get_db
from app.schemas.approval_note import (
    ActiveLetterheadOut,
    ApprovalNoteCreate,
    ApprovalNoteOut,
    ApprovalNoteTypeCreate,
    ApprovalNoteTypeOut,
    ApprovalNoteTypeUpdate,
    OnlyOfficeConfigOut,
    OnlyOfficeForceSaveIn,
    OnlyOfficeForceSaveOut,
    TemplateOut,
)
from app.services import (
    approval_note_service as notes,
    approval_note_type_service as note_types,
    onlyoffice_service,
    template_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["approval-notes"])
DbSession = Annotated[Session, Depends(get_db)]

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _safe_download_name(title: str, note_id: int) -> str:
    import re

    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-")[:80] or "approval-note"
    return f"{slug}-{note_id}.docx"


# ===================== ADMIN: LETTERHEAD ===================== #
@router.post("/admin/approval-notes/letterhead", response_model=TemplateOut, status_code=201)
def upload_letterhead(
    admin: AdminUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
):
    data = file.file.read()
    try:
        return template_service.upload_letterhead(
            db, admin, filename=file.filename or "letterhead.docx", data=data, name=name
        )
    except template_service.TemplateTooLargeError as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc))
    except template_service.InvalidDocxError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc))


@router.get("/admin/approval-notes/letterhead", response_model=ActiveLetterheadOut)
def get_letterhead(admin: AdminUser, db: DbSession) -> ActiveLetterheadOut:
    template = template_service.get_active_letterhead(db, admin)
    return ActiveLetterheadOut(
        active=template is not None,
        template=TemplateOut.model_validate(template) if template else None,
    )


@router.get("/admin/approval-notes/letterhead/download")
def download_letterhead(admin: AdminUser, db: DbSession) -> Response:
    template = template_service.get_active_letterhead(db, admin)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active letterhead.")
    data = template_service.read_template_bytes(template)
    return Response(
        content=data,
        media_type=DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{template.original_filename}"'},
    )


# ===================== ADMIN: TYPES ===================== #
@router.get("/admin/approval-notes/types", response_model=list[ApprovalNoteTypeOut])
def admin_list_types(admin: AdminUser, db: DbSession):
    return note_types.list_types(db, admin)


@router.post("/admin/approval-notes/types", response_model=ApprovalNoteTypeOut, status_code=201)
def admin_create_type(payload: ApprovalNoteTypeCreate, admin: AdminUser, db: DbSession):
    try:
        return note_types.create_type(
            db, admin, name=payload.name, description=payload.description,
            display_order=payload.display_order,
        )
    except note_types.InvalidApprovalNoteTypeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/admin/approval-notes/types/{type_id}", response_model=ApprovalNoteTypeOut)
def admin_update_type(
    type_id: int, payload: ApprovalNoteTypeUpdate, admin: AdminUser, db: DbSession
):
    try:
        return note_types.update_type(db, admin, type_id, payload.model_dump(exclude_unset=True))
    except note_types.InvalidApprovalNoteTypeError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ===================== USER: TYPES (selectable) ===================== #
@router.get("/approval-notes/types", response_model=list[ApprovalNoteTypeOut])
def list_selectable_types(current_user: CurrentUser, db: DbSession):
    return note_types.list_types(db, current_user, active_only=True)


# ===================== USER: NOTES ===================== #
@router.post("/approval-notes", response_model=ApprovalNoteOut, status_code=201)
def create_note(payload: ApprovalNoteCreate, current_user: CurrentUser, db: DbSession):
    try:
        return notes.create_approval_note(
            db, current_user,
            approval_note_type_id=payload.approval_note_type_id,
            parameters=payload.parameters,
            title_override=payload.title,
        )
    except note_types.InvalidApprovalNoteTypeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except template_service.NoActiveTemplateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("Approval Note creation failed")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not create the Approval Note.")


@router.get("/approval-notes", response_model=list[ApprovalNoteOut])
def list_notes(current_user: CurrentUser, db: DbSession):
    return notes.list_notes(db, current_user)


@router.get("/approval-notes/{note_id}", response_model=ApprovalNoteOut)
def get_note(note_id: int, current_user: CurrentUser, db: DbSession):
    return _load_note(db, current_user, note_id)


@router.get("/approval-notes/{note_id}/download")
def download_note(note_id: int, current_user: CurrentUser, db: DbSession) -> Response:
    note = _load_note(db, current_user, note_id)
    data = notes.read_note_bytes(note)
    return Response(
        content=data,
        media_type=DOCX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{_safe_download_name(note.title, note.id)}"'
        },
    )


@router.get("/approval-notes/{note_id}/editor-config", response_model=OnlyOfficeConfigOut)
def editor_config(note_id: int, current_user: CurrentUser, db: DbSession) -> OnlyOfficeConfigOut:
    note = _load_note(db, current_user, note_id)
    from app.core.config import settings

    if not settings.onlyoffice_jwt_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ONLYOFFICE is not configured.")
    config = onlyoffice_service.build_editor_config(note, current_user, mode="edit")
    return OnlyOfficeConfigOut(
        config=config,
        onlyoffice_url=settings.onlyoffice_url,
        document_server_api_js=f"{settings.onlyoffice_url.rstrip('/')}/web-apps/apps/api/documents/api.js",
    )


@router.post(
    "/approval-notes/{note_id}/force-save",
    response_model=OnlyOfficeForceSaveOut,
)
def force_save_note(
    note_id: int,
    payload: OnlyOfficeForceSaveIn,
    current_user: CurrentUser,
    db: DbSession,
) -> OnlyOfficeForceSaveOut:
    note = _load_note(db, current_user, note_id)
    key_prefix = f"an-{note.id}-v"
    try:
        key_version = int(payload.document_key.removeprefix(key_prefix))
    except ValueError:
        key_version = 0
    if not payload.document_key.startswith(key_prefix) or not 1 <= key_version <= note.document_version:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid editor session key.")
    try:
        result = onlyoffice_service.force_save(note, payload.document_key)
    except onlyoffice_service.OnlyOfficeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    if result["error_code"] not in (0, 4):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, result["message"])
    return OnlyOfficeForceSaveOut(**result)


def _load_note(db: Session, current_user, note_id: int):
    try:
        return notes.get_note(db, current_user, note_id)
    except notes.ApprovalNoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except notes.ApprovalNoteAccessError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
