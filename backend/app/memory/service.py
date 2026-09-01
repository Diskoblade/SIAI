"""Private memory persistence using the shared authorized vector layer."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.memory.classifier import ClassifiedMemory, classify_message
from app.models.document import Document, DocumentChunk, MemoryCategory, Visibility
from app.models.user import User
from app.rag import ingestion
from app.rag.vector_store import get_vector_store


class MemoryNotFoundError(Exception):
    pass


_CATEGORY_TITLES = {
    MemoryCategory.CONVERSATION: "Conversation memory",
    MemoryCategory.PROJECT_DECISION: "Memory - Project decision",
    MemoryCategory.USER_NOTE: "Memory - User note",
    MemoryCategory.PREFERENCE: "Memory - Preference",
    MemoryCategory.GENERATED_ARTIFACT: "Memory - Generated artifact",
}


def save_memory(
    db: Session,
    *,
    user: User,
    content: str,
    category: MemoryCategory,
) -> Document:
    normalized = " ".join(content.split()).strip()
    existing = db.scalar(
        select(Document)
        .join(DocumentChunk)
        .where(
            Document.owner_user_id == user.id,
            Document.document_type == "memory",
            DocumentChunk.text == normalized,
        )
    )
    if existing is not None:
        return existing

    return ingestion.ingest_text(
        db,
        title=_CATEGORY_TITLES[category],
        text=normalized,
        access_scope=[],
        owner_department_id=user.department_id,
        document_type="memory",
        classification="private",
        created_by=user.id,
        owner_user_id=user.id,
        visibility=Visibility.PRIVATE,
        memory_category=category.value,
    )


def capture_message(db: Session, *, user: User, message: str) -> Document | None:
    classified: ClassifiedMemory | None = classify_message(message)
    if classified is None:
        return None
    return save_memory(
        db,
        user=user,
        content=classified.content,
        category=classified.category,
    )


def list_memories(db: Session, *, user: User) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(
                Document.owner_user_id == user.id,
                Document.document_type == "memory",
            )
            .order_by(Document.created_at.desc())
        )
    )


def delete_memory(db: Session, *, user: User, memory_id: str) -> None:
    memory = db.get(Document, memory_id)
    if (
        memory is None
        or memory.document_type != "memory"
        or memory.owner_user_id != user.id
    ):
        raise MemoryNotFoundError()
    get_vector_store().delete_document(db, memory.id)
    db.delete(memory)
    db.commit()
