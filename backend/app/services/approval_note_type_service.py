"""ApprovalNoteTypeService — administrator-managed Approval Note categories.

Titles are never hard-coded in application logic; admins add/edit/deactivate
types. All queries are company-scoped from the authenticated user.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.approval_note import ApprovalNoteType
from app.models.user import User

DEFAULT_TYPES = [
    "Purchase Requisition Approval Note",
    "Capital Expenditure (CAPEX) Approval Note",
    "Operating Expenditure (OPEX) Approval Note",
    "Tender / Bid Evaluation Approval Note",
    "Single Tender / Proprietary Procurement Approval Note",
    "Work Order / Service Contract Award Approval Note",
    "Contract Extension / Amendment Approval Note",
    "Technical Change / Modification Approval Note",
    "Maintenance / Shutdown Work Approval Note",
]


class ApprovalNoteTypeError(Exception):
    pass


class InvalidApprovalNoteTypeError(ApprovalNoteTypeError):
    pass


def _company_id(user: User) -> int:
    return settings.default_company_id


def list_types(db: Session, user: User, *, active_only: bool = False) -> list[ApprovalNoteType]:
    stmt = select(ApprovalNoteType).where(ApprovalNoteType.company_id == _company_id(user))
    if active_only:
        stmt = stmt.where(ApprovalNoteType.is_active.is_(True))
    stmt = stmt.order_by(ApprovalNoteType.display_order, ApprovalNoteType.name)
    return list(db.scalars(stmt))


def get_type(
    db: Session, user: User, type_id: int, *, active_only: bool = False
) -> ApprovalNoteType | None:
    stmt = select(ApprovalNoteType).where(
        ApprovalNoteType.id == type_id,
        ApprovalNoteType.company_id == _company_id(user),
    )
    if active_only:
        stmt = stmt.where(ApprovalNoteType.is_active.is_(True))
    return db.scalar(stmt)


def require_selectable_type(db: Session, user: User, type_id: int) -> ApprovalNoteType:
    """A normal user may only select an ACTIVE type in their company."""
    note_type = get_type(db, user, type_id, active_only=True)
    if note_type is None:
        raise InvalidApprovalNoteTypeError("Invalid or inactive Approval Note type.")
    return note_type


def create_type(
    db: Session,
    user: User,
    *,
    name: str,
    description: str | None = None,
    display_order: int | None = None,
) -> ApprovalNoteType:
    name = (name or "").strip()
    if not name:
        raise InvalidApprovalNoteTypeError("A name is required.")
    if display_order is None:
        existing = list_types(db, user)
        display_order = (max((t.display_order for t in existing), default=0) + 1)
    note_type = ApprovalNoteType(
        company_id=_company_id(user),
        name=name,
        description=(description or None),
        display_order=display_order,
        is_active=True,
        created_by=user.id,
    )
    db.add(note_type)
    db.commit()
    db.refresh(note_type)
    return note_type


def update_type(db: Session, user: User, type_id: int, changes: dict) -> ApprovalNoteType:
    note_type = get_type(db, user, type_id)
    if note_type is None:
        raise InvalidApprovalNoteTypeError("Approval Note type not found.")
    if "name" in changes and changes["name"] is not None:
        name = str(changes["name"]).strip()
        if not name:
            raise InvalidApprovalNoteTypeError("A name is required.")
        note_type.name = name
    if "description" in changes:
        note_type.description = (changes["description"] or None)
    if "display_order" in changes and changes["display_order"] is not None:
        note_type.display_order = int(changes["display_order"])
    if "is_active" in changes and changes["is_active"] is not None:
        note_type.is_active = bool(changes["is_active"])
    db.commit()
    db.refresh(note_type)
    return note_type


def seed_default_types(db: Session, company_id: int | None = None) -> int:
    """Insert the default Approval Note types for a company if none exist."""
    company_id = company_id or settings.default_company_id
    exists = db.scalar(
        select(ApprovalNoteType.id).where(ApprovalNoteType.company_id == company_id).limit(1)
    )
    if exists is not None:
        return 0
    for order, name in enumerate(DEFAULT_TYPES, start=1):
        db.add(
            ApprovalNoteType(
                company_id=company_id,
                name=name,
                display_order=order,
                is_active=True,
            )
        )
    db.commit()
    return len(DEFAULT_TYPES)
