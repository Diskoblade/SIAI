"""Document management routes.

Upload authorization and the owning department are decided by the backend from
the authenticated user (never trusted from the request). Listing is scoped to
the caller's allowed scopes.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser
from app.database import get_db
from app.models.department import Department
from app.models.document import Document, Visibility
from app.rag import ingestion
from app.schemas.document import (
    DocumentSummary,
    DocumentTextIngest,
    DocumentVisibilityUpdate,
)
from app.services import document_service
from app.services.authorization_service import build_user_context, can_access_content

router = APIRouter(prefix="/api/documents", tags=["documents"])

DbSession = Annotated[Session, Depends(get_db)]

_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB safety cap
_MAX_TITLE_LENGTH = 400
_TEXT_TO_FILE_THRESHOLD = 200


def _handle_auth_errors(exc: Exception) -> None:
    if isinstance(exc, document_service.UploadNotAuthorizedError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, document_service.InvalidDepartmentError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid department.")
    raise exc


def _effective_visibility(document: Document) -> Visibility:
    if document.visibility is not None:
        return document.visibility
    scopes = set(document.access_scope or [])
    return Visibility.COMMON if scopes == {"common"} else Visibility.DEPARTMENT


def _serialize_document(db: Session, document: Document) -> DocumentSummary:
    department = (
        db.get(Department, document.owner_department_id)
        if document.owner_department_id is not None
        else None
    )
    return DocumentSummary(
        id=document.id,
        title=document.title,
        owner_department_id=document.owner_department_id,
        owner_user_id=document.owner_user_id,
        visibility=_effective_visibility(document),
        department_name=department.name if department else None,
        shared_at=document.shared_at,
        document_type=document.document_type,
        classification=document.classification,
        access_scope=list(document.access_scope or []),
        source_filename=document.source_filename,
        status=document.status,
        chunk_count=document.chunk_count,
        created_at=document.created_at,
    )


@router.get("", response_model=list[DocumentSummary])
def list_documents(
    current_user: CurrentUser,
    db: DbSession,
    view: Annotated[Literal["mine", "shared"], Query()] = "mine",
) -> list[DocumentSummary]:
    """List owned files or non-private department/common knowledge."""
    docs = db.scalars(
        select(Document)
        .where(Document.document_type != "memory")
        .order_by(Document.created_at.desc())
    ).all()
    if view == "mine":
        visible = [document for document in docs if document.owner_user_id == current_user.id]
    else:
        context = build_user_context(db, current_user)
        visible = [
            document
            for document in docs
            if _effective_visibility(document) != Visibility.PRIVATE
            and can_access_content(
                context=context,
                owner_user_id=document.owner_user_id,
                department_id=document.owner_department_id,
                visibility=document.visibility,
                legacy_access_scope=list(document.access_scope or []),
            )
        ]
    return [_serialize_document(db, document) for document in visible]


@router.post("", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
def upload_document(
    current_user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    department_id: Annotated[int | None, Form()] = None,
    access_scope: Annotated[str | None, Form()] = None,
) -> DocumentSummary:
    """Upload and ingest a document (multipart)."""
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A title is required.")
    if len(clean_title) > _MAX_TITLE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Title must be {_MAX_TITLE_LENGTH} characters or fewer.",
        )

    requested_scope = (
        [s.strip() for s in access_scope.split(",") if s.strip()] if access_scope else None
    )
    try:
        resolved = document_service.resolve_upload_authorization(
            db,
            current_user,
            requested_department_id=department_id,
            requested_access_scope=requested_scope,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_auth_errors(exc)

    data = file.file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 20 MB limit.",
        )

    try:
        filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        document = ingestion.ingest_document(
            db,
            title=clean_title,
            access_scope=resolved.access_scope,
            owner_department_id=resolved.owner_department_id,
            filename=filename or f"{clean_title}.txt",
            data=data,
            created_by=current_user.id,
            owner_user_id=resolved.owner_user_id,
            visibility=resolved.visibility,
        )
    except ingestion.UnsupportedFileType as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
    except (ingestion.DocumentParseError, ingestion.EmptyDocumentError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    except ingestion.VectorIndexingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return _serialize_document(db, document)


@router.post("/text", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
def ingest_text_document(
    payload: DocumentTextIngest, current_user: CurrentUser, db: DbSession
) -> DocumentSummary:
    """Ingest raw text (no file) — convenient for seeding and testing."""
    if payload.document_type.strip().lower() == "memory":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use the memory API to create private conversation memories.",
        )
    try:
        resolved = document_service.resolve_upload_authorization(
            db,
            current_user,
            requested_department_id=payload.department_id,
            requested_access_scope=payload.access_scope,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_auth_errors(exc)

    clean_text = payload.text.strip()
    if len(clean_text) > _TEXT_TO_FILE_THRESHOLD:
        document = ingestion.ingest_document(
            db,
            title=payload.title,
            access_scope=resolved.access_scope,
            owner_department_id=resolved.owner_department_id,
            filename=f"{payload.title}.txt",
            data=payload.text.encode("utf-8"),
            document_type=payload.document_type,
            classification=payload.classification,
            created_by=current_user.id,
            owner_user_id=resolved.owner_user_id,
            visibility=resolved.visibility,
        )
    else:
        document = ingestion.ingest_text(
            db,
            title=payload.title,
            text=payload.text,
            access_scope=resolved.access_scope,
            owner_department_id=resolved.owner_department_id,
            document_type=payload.document_type,
            classification=payload.classification,
            created_by=current_user.id,
            owner_user_id=resolved.owner_user_id,
            visibility=resolved.visibility,
        )
    return _serialize_document(db, document)


@router.patch("/{document_id}/visibility", response_model=DocumentSummary)
def update_visibility(
    document_id: str,
    payload: DocumentVisibilityUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> DocumentSummary:
    try:
        document = document_service.update_document_visibility(
            db,
            user=current_user,
            document_id=document_id,
            visibility=payload.visibility,
        )
    except document_service.DocumentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    except document_service.VisibilityNotAuthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except document_service.VisibilityUpdateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return _serialize_document(db, document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> Response:
    try:
        document_service.delete_document(
            db,
            user=current_user,
            document_id=document_id,
        )
    except document_service.DocumentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    except document_service.DocumentDeleteNotAuthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except document_service.DocumentDeleteError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
