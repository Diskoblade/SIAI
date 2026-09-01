"""Owner-first document upload and visibility authorization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.document import Document, Visibility
from app.models.user import User, UserRole
from app.rag.vector_store import get_vector_store
from app.services.authorization_service import COMMON_SCOPE, department_scope


class UploadNotAuthorizedError(Exception):
    pass


class InvalidDepartmentError(Exception):
    pass


class DocumentNotFoundError(Exception):
    pass


class VisibilityNotAuthorizedError(Exception):
    pass


class VisibilityUpdateError(Exception):
    pass


class DocumentDeleteNotAuthorizedError(Exception):
    pass


class DocumentDeleteError(Exception):
    pass


@dataclass(frozen=True)
class ResolvedUpload:
    owner_user_id: int
    owner_department_id: int | None
    visibility: Visibility
    access_scope: list[str]


def _normalize_scopes(scopes: list[str]) -> list[str]:
    normalized: list[str] = []
    for scope in scopes:
        value = (scope or "").strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _department_for_scope(db: Session, scope: str) -> Department | None:
    return next(
        (
            department
            for department in db.scalars(select(Department))
            if department_scope(department) == scope
        ),
        None,
    )


def resolve_upload_authorization(
    db: Session,
    user: User,
    *,
    requested_department_id: int | None,
    requested_access_scope: list[str] | None,
) -> ResolvedUpload:
    """Resolve upload metadata exclusively from the authenticated user.

    Normal users and department managers always create private content. Admins
    retain an explicit common/department publishing workflow for managed
    organizational knowledge.
    """
    requested_scopes = _normalize_scopes(requested_access_scope or [])

    if user.role != UserRole.admin:
        if requested_department_id is not None:
            raise UploadNotAuthorizedError(
                "Your upload department is assigned by the server."
            )
        if requested_scopes:
            raise UploadNotAuthorizedError(
                "User uploads are private by default; share them after upload."
            )
        return ResolvedUpload(
            owner_user_id=user.id,
            owner_department_id=user.department_id,
            visibility=Visibility.PRIVATE,
            access_scope=[],
        )

    department = None
    if requested_department_id is not None:
        department = db.get(Department, requested_department_id)
        if department is None:
            raise InvalidDepartmentError()

    if requested_scopes:
        if requested_scopes == [COMMON_SCOPE]:
            if department is not None:
                raise UploadNotAuthorizedError(
                    "Common content cannot be assigned to a department."
                )
        elif len(requested_scopes) == 1:
            scope_department = _department_for_scope(db, requested_scopes[0])
            if scope_department is None:
                raise InvalidDepartmentError()
            if department is not None and department.id != scope_department.id:
                raise UploadNotAuthorizedError(
                    "The requested department and scope do not match."
                )
            department = scope_department
        else:
            raise UploadNotAuthorizedError(
                "New content can target one department or the common scope."
            )

    if department is None:
        return ResolvedUpload(
            owner_user_id=user.id,
            owner_department_id=None,
            visibility=Visibility.COMMON,
            access_scope=[COMMON_SCOPE],
        )

    return ResolvedUpload(
        owner_user_id=user.id,
        owner_department_id=department.id,
        visibility=Visibility.DEPARTMENT,
        access_scope=[department_scope(department)],
    )


def update_document_visibility(
    db: Session,
    *,
    user: User,
    document_id: str,
    visibility: Visibility,
) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.document_type == "memory":
        raise DocumentNotFoundError()
    if document.owner_user_id != user.id:
        raise VisibilityNotAuthorizedError(
            "Only the document owner can change its visibility."
        )
    if visibility == Visibility.COMMON and user.role != UserRole.admin:
        raise VisibilityNotAuthorizedError(
            "Only administrators can publish common content."
        )

    now = datetime.now(timezone.utc)
    if visibility == Visibility.PRIVATE:
        access_scope: list[str] = []
        shared_at = None
    elif visibility == Visibility.DEPARTMENT:
        if user.department_id is None:
            raise VisibilityUpdateError("You must belong to a department before sharing.")
        if document.owner_department_id != user.department_id:
            raise VisibilityUpdateError(
                "This file belongs to a different department assignment and cannot be shared."
            )
        department = db.get(Department, user.department_id)
        if department is None:
            raise VisibilityUpdateError("Your department is not configured.")
        access_scope = [department_scope(department)]
        shared_at = now
    else:
        access_scope = [COMMON_SCOPE]
        shared_at = now

    document.visibility = visibility
    document.access_scope = access_scope
    document.shared_at = shared_at
    document.updated_at = now
    for chunk in document.chunks:
        chunk.owner_user_id = document.owner_user_id
        chunk.department_id = document.owner_department_id
        chunk.visibility = visibility
        chunk.access_scope = list(access_scope)

    try:
        db.flush()
        # SQLite is a no-op. Qdrant replaces payload metadata without
        # regenerating embeddings.
        get_vector_store().upsert(db, document.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise VisibilityUpdateError("Vector visibility metadata could not be updated.") from exc

    db.refresh(document)
    return document


def delete_document(db: Session, *, user: User, document_id: str) -> None:
    """Delete an owned knowledge file from SQL and the configured vector store."""
    document = db.get(Document, document_id)
    if document is None or document.document_type == "memory":
        raise DocumentNotFoundError()
    if document.owner_user_id != user.id:
        raise DocumentDeleteNotAuthorizedError(
            "Only the document owner can delete this file."
        )

    store = get_vector_store()
    vector_deleted = False
    try:
        # Remove external points first. The SQL row remains intact if this fails.
        store.delete_document(db, document.id)
        vector_deleted = True
        db.delete(document)
        db.commit()
    except Exception as exc:
        db.rollback()
        if vector_deleted:
            try:
                # A failed SQL commit must not leave a still-visible database row
                # missing from Qdrant.
                store.upsert(db, document_id)
            except Exception:  # noqa: BLE001 - preserve the original failure
                pass
        raise DocumentDeleteError(
            "The file could not be removed from the knowledge store."
        ) from exc
