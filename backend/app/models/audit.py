"""Audit log for RAG queries (spec #26).

Records who asked what and which documents were accessed. Deliberately stores
NO passwords, JWTs, or secrets.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RagAuditLog(Base):
    __tablename__ = "rag_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    department_scope: Mapped[str | None] = mapped_column(String(80), nullable=True)
    allowed_scopes: Mapped[list] = mapped_column(JSON, default=list)

    question: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_strategy: Mapped[str] = mapped_column(String(60), default="hybrid")
    document_ids_accessed: Mapped[list] = mapped_column(JSON, default=list)
    retrieval_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    response_status: Mapped[str] = mapped_column(String(40), default="ok")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
