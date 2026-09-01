"""Department schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DepartmentPublic(BaseModel):
    """Safe department representation for the signup dropdown and profiles.

    Deliberately excludes `vector_collection` — the mapping from department to
    VectorDB collection is a server-side authorization detail and is not
    exposed to the frontend.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class DepartmentAdmin(BaseModel):
    """Fuller department view, including the collection, for admin tooling."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    vector_collection: str
    created_at: datetime
