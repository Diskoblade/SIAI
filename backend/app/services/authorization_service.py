"""Centralized authorization logic.

All department -> scope/collection resolution lives here so authorization
rules are not scattered across the codebase. The frontend never influences
these decisions; they are derived from the authenticated user loaded from the
database.

This is deterministic backend code (never LLM reasoning). It is the single
source of truth for "what departmental data may this user reach?".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.document import Visibility
from app.models.user import User, UserRole

# Every user can additionally see shared/common documents.
COMMON_SCOPE = "common"

# Capability tiers used for document upload authorization (spec #3). Mapped
# from the existing role vocabulary so we do not rebuild the role model.
CAP_ADMIN = "ADMIN"
CAP_DEPARTMENT_ADMIN = "DEPARTMENT_ADMIN"
CAP_OFFICER = "OFFICER"
CAP_VIEWER = "VIEWER"

_ROLE_TO_CAPABILITY = {
    UserRole.admin: CAP_ADMIN,
    UserRole.manager: CAP_DEPARTMENT_ADMIN,
    UserRole.user: CAP_OFFICER,
}


class NotAuthorizedError(Exception):
    """Raised when a user has no authorized department/collection."""


def department_scope(department: Department) -> str:
    """Derive a stable string scope from a department (e.g. 'Finance' -> 'finance').

    Scopes are derived from trusted DB state (the department name), never from
    anything the client sends.
    """
    return _slugify(department.name)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def resolve_capability(user: User) -> str:
    """Map the user's role to an upload-capability tier."""
    return _ROLE_TO_CAPABILITY.get(user.role, CAP_VIEWER)


@dataclass(frozen=True)
class UserContext:
    """Trusted, backend-resolved authorization context for RAG execution.

    Mirrors the shape the RAG spec requires and is passed into every RAG run.
    The agentic workflow must never operate without one of these.
    """

    user_id: int
    department_id: int | None
    department_scope: str | None
    role: str
    capability: str
    allowed_scopes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "department_id": self.department_scope,  # spec uses the string scope here
            "role": self.role,
            "capability": self.capability,
            "allowed_scopes": self.allowed_scopes,
        }


def resolve_allowed_scopes(db: Session, user: User) -> list[str]:
    """Return the list of data scopes the user may retrieve from.

    = [the user's own department scope] + [COMMON_SCOPE]. Sourced entirely from
    the database; the LLM is never asked to compute permissions.
    """
    scopes: list[str] = []
    if user.department_id is not None:
        department = db.get(Department, user.department_id)
        if department is not None:
            scopes.append(department_scope(department))
    scopes.append(COMMON_SCOPE)
    # De-duplicate, preserve order.
    seen: set[str] = set()
    return [s for s in scopes if not (s in seen or seen.add(s))]


def build_user_context(db: Session, user: User) -> UserContext:
    """Assemble the full trusted context for a user (identity + scopes)."""
    dept = db.get(Department, user.department_id) if user.department_id is not None else None
    return UserContext(
        user_id=user.id,
        department_id=user.department_id,
        department_scope=department_scope(dept) if dept is not None else None,
        role=user.role.value,
        capability=resolve_capability(user),
        allowed_scopes=resolve_allowed_scopes(db, user),
    )


def can_access_content(
    *,
    context: UserContext,
    owner_user_id: int | None,
    department_id: int | None,
    visibility: Visibility | str | None,
    legacy_access_scope: list[str] | None = None,
) -> bool:
    """Apply the owner-first access rule to document or vector metadata.

    A null visibility is accepted only for rows created before this feature and
    uses the previous scope-list rule. New content must always provide an
    explicit visibility.
    """
    value = visibility.value if isinstance(visibility, Visibility) else visibility
    if value == Visibility.PRIVATE.value:
        return owner_user_id is not None and owner_user_id == context.user_id
    if value == Visibility.DEPARTMENT.value:
        return (
            department_id is not None
            and context.department_id is not None
            and department_id == context.department_id
        )
    if value == Visibility.COMMON.value:
        return True
    return bool(set(legacy_access_scope or []) & set(context.allowed_scopes))


def get_authorized_vector_collection(db: Session, current_user: User) -> str:
    """Resolve the single VectorDB collection the user may query.

    Retained from the original auth milestone (used by the legacy /rag/query
    response for backward compatibility). Derived purely from the user's
    server-side department assignment.
    """
    if current_user.department_id is None:
        raise NotAuthorizedError("User has no department assigned.")

    department = db.get(Department, current_user.department_id)
    if department is None or not department.vector_collection:
        raise NotAuthorizedError("Assigned department is not configured for data access.")

    return department.vector_collection
