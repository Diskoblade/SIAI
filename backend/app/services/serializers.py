"""Helpers that convert ORM users into safe API schemas.

Centralizing this guarantees a password hash can never accidentally be
serialized into a response, and fills in the derived `department_name`.
"""

from __future__ import annotations

from app.models.user import User
from app.schemas.user import UserAdminView, UserMe, UserPublic


def _department_name(user: User) -> str | None:
    return user.department.name if user.department is not None else None


def to_user_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        department_id=user.department_id,
        department_name=_department_name(user),
        role=user.role,
    )


def to_user_me(user: User) -> UserMe:
    return UserMe(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        department_id=user.department_id,
        department_name=_department_name(user),
        role=user.role,
        status=user.status,
    )


def to_user_admin(user: User) -> UserAdminView:
    return UserAdminView(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        department_id=user.department_id,
        department_name=_department_name(user),
        role=user.role,
        status=user.status,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
