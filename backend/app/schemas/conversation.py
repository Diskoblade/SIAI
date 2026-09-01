"""Schemas for owner-isolated, multi-turn conversation sessions."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.conversation import ConversationRole
from app.schemas.rag import Citation, PresentationSpec, ScientificCalculation


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=120)


class ConversationSummary(BaseModel):
    id: str
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationMessageSummary(BaseModel):
    id: str
    role: ConversationRole
    content: str
    answer_source: str | None = None
    evidence_status: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    documents_used: list[str] = Field(default_factory=list)
    authorized_collection: str | None = None
    presentation: PresentationSpec | None = None
    calculation: ScientificCalculation | None = None
    created_at: datetime
