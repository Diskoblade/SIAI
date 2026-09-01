"""Admin routes — user management. Every route requires an admin (server-side).

Authorization here relies on the `AdminUser` dependency, which reloads the
caller from the DB and checks role == admin. Hiding the admin page in the
frontend is NOT a substitute for these checks.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import AdminUser
from app.database import get_db
from app.models.department import Department
from app.models.user import User, UserRole, UserStatus
from app.schemas.admin import AdminUserUpdate
from app.schemas.user import UserAdminView
from app.services.serializers import to_user_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/users", response_model=list[UserAdminView])
def list_users(
    admin: AdminUser,
    db: DbSession,
    status_filter: Annotated[UserStatus | None, Query(alias="status")] = None,
) -> list[UserAdminView]:
    """List all users, most recent first. Optionally filter by status."""
    stmt = select(User)
    if status_filter is not None:
        stmt = stmt.where(User.status == status_filter)
    stmt = stmt.order_by(User.created_at.desc())
    return [to_user_admin(u) for u in db.scalars(stmt)]


@router.patch("/users/{user_id}", response_model=UserAdminView)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    admin: AdminUser,
    db: DbSession,
) -> UserAdminView:
    """Approve/reject/disable, reassign department, or change a user's role."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Guard against an admin locking themselves out of the admin area.
    if user.id == admin.id:
        if payload.role is not None and payload.role is not UserRole.admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot remove your own administrator role.",
            )
        if payload.status is not None and payload.status is not UserStatus.approved:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot change your own account away from approved.",
            )

    if payload.department_id is not None:
        department = db.get(Department, payload.department_id)
        if department is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid department.",
            )
        user.department_id = payload.department_id

    if payload.role is not None:
        user.role = payload.role

    if payload.status is not None:
        user.status = payload.status

    db.commit()
    db.refresh(user)
    return to_user_admin(user)
