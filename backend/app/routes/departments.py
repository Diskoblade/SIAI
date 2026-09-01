"""Public department listing — used to populate the signup dropdown.

Only id and name are exposed (see DepartmentPublic); the VectorDB collection
mapping is never sent to the client.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.department import Department
from app.schemas.department import DepartmentPublic

router = APIRouter(prefix="/api/departments", tags=["departments"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[DepartmentPublic])
def list_departments(db: DbSession) -> list[Department]:
    return list(db.scalars(select(Department).order_by(Department.name)))
