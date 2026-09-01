"""Private conversation-memory API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import MemoryCategory, Visibility

MAX_MEMORY_CONTENT_LENGTH = 10_000


class MemoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(min_length=12, max_length=MAX_MEMORY_CONTENT_LENGTH)
    category: MemoryCategory = MemoryCategory.USER_NOTE


class MemorySummary(BaseModel):
    id: str
    content: str
    category: MemoryCategory
    visibility: Visibility
    created_at: datetime
