"""Authenticated, owner-only conversation-memory routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser
from app.database import get_db
from app.memory import service
from app.models.document import MemoryCategory, Visibility
from app.schemas.memory import MemoryCreate, MemorySummary

router = APIRouter(prefix="/api/memories", tags=["memories"])
DbSession = Annotated[Session, Depends(get_db)]


def _summary(memory) -> MemorySummary:
    content = memory.chunks[0].text if memory.chunks else ""
    return MemorySummary(
        id=memory.id,
        content=content,
        category=MemoryCategory(memory.memory_category or MemoryCategory.CONVERSATION.value),
        visibility=memory.visibility or Visibility.PRIVATE,
        created_at=memory.created_at,
    )


@router.get("", response_model=list[MemorySummary])
def list_user_memories(current_user: CurrentUser, db: DbSession) -> list[MemorySummary]:
    return [_summary(memory) for memory in service.list_memories(db, user=current_user)]


@router.post("", response_model=MemorySummary, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreate, current_user: CurrentUser, db: DbSession
) -> MemorySummary:
    memory = service.save_memory(
        db,
        user=current_user,
        content=payload.content,
        category=payload.category,
    )
    return _summary(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: str, current_user: CurrentUser, db: DbSession
) -> Response:
    try:
        service.delete_memory(db, user=current_user, memory_id=memory_id)
    except service.MemoryNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
