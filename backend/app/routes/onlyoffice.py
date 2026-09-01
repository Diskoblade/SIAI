"""ONLYOFFICE Document Server integration routes.

  * GET  /api/onlyoffice/documents/{note_id}/file  — the Document Server fetches
    the DOCX here, authorized by a short-lived signed token (no user session).
  * POST /api/onlyoffice/callback/{note_id}         — the Document Server posts
    save callbacks here; validated by our access token AND the ONLYOFFICE JWT.
  * GET  /api/integrations/onlyoffice/health        — status for the admin UI.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser
from app.database import get_db
from app.models.approval_note import ApprovalNote
from app.schemas.approval_note import OnlyOfficeHealthOut
from app.services import approval_note_service, document_storage, onlyoffice_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["onlyoffice"])
DbSession = Annotated[Session, Depends(get_db)]

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _note_for_token(db: Session, note_id: int, token: str, purpose: str) -> ApprovalNote:
    try:
        token_note_id = onlyoffice_service.verify_access_token(token, purpose)
    except onlyoffice_service.CallbackAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))
    if token_note_id != note_id:  # token is bound to exactly one note
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token does not match document.")
    note = db.get(ApprovalNote, note_id)
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return note


@router.get("/api/onlyoffice/documents/{note_id}/file")
def onlyoffice_file(note_id: int, db: DbSession, token: Annotated[str, Query()]) -> Response:
    note = _note_for_token(db, note_id, token, "file")
    try:
        data = document_storage.read_bytes("approval_notes", note.storage_key)
    except document_storage.StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document file missing.")
    return Response(content=data, media_type=DOCX_MIME)


@router.post("/api/onlyoffice/callback/{note_id}")
def onlyoffice_callback(
    note_id: int,
    db: DbSession,
    token: Annotated[str, Query()],
    payload: Annotated[dict, Body()],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    note = _note_for_token(db, note_id, token, "callback")
    # Verify the ONLYOFFICE JWT on the callback (body token or Authorization).
    try:
        claims = onlyoffice_service.validate_callback(payload, authorization)
    except onlyoffice_service.OnlyOfficeError as exc:
        logger.warning("Rejected ONLYOFFICE callback for note %s: %s", note_id, exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid callback signature.")
    return onlyoffice_service.process_callback(db, note, claims)


@router.get("/api/integrations/onlyoffice/health", response_model=OnlyOfficeHealthOut)
def onlyoffice_health(current_user: CurrentUser) -> OnlyOfficeHealthOut:
    return OnlyOfficeHealthOut(**onlyoffice_service.check_health())
