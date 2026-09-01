"""Document schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import Visibility


class DocumentTextIngest(BaseModel):
    """JSON path for ingesting raw text (handy for seeding/testing)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=400)
    text: str = Field(min_length=1)
    # Only honored for ADMIN uploaders; ignored for department admins (their
    # own department is used). Never trusted for normal users.
    department_id: int | None = None
    access_scope: list[str] | None = None
    document_type: str = "document"
    classification: str = "internal"


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    owner_department_id: int | None
    owner_user_id: int | None
    visibility: Visibility
    department_name: str | None = None
    shared_at: datetime | None = None
    document_type: str
    classification: str
    access_scope: list[str]
    source_filename: str | None
    status: str
    chunk_count: int
    created_at: datetime


class DocumentVisibilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visibility: Visibility
