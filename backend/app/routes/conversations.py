"""Owner-only conversation session management routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser
from app.database import get_db
from app.models.conversation import Conversation, ConversationMessage
from app.schemas.conversation import (
    ConversationCreate,
    ConversationMessageSummary,
    ConversationSummary,
)
from app.services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
DbSession = Annotated[Session, Depends(get_db)]


def _summary(conversation: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        message_count=conversation.message_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message(message: ConversationMessage) -> ConversationMessageSummary:
    return ConversationMessageSummary(
        id=message.id,
        role=message.role,
        content=message.content,
        answer_source=message.answer_source,
        evidence_status=message.evidence_status,
        citations=list(message.citations or []),
        documents_used=list(message.documents_used or []),
        authorized_collection=message.authorized_collection,
        presentation=message.presentation,
        calculation=message.calculation,
        created_at=message.created_at,
    )


@router.get("", response_model=list[ConversationSummary])
def list_user_conversations(
    current_user: CurrentUser, db: DbSession
) -> list[ConversationSummary]:
    return [
        _summary(conversation)
        for conversation in conversation_service.list_conversations(db, user=current_user)
    ]


@router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
def create_user_conversation(
    payload: ConversationCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ConversationSummary:
    return _summary(
        conversation_service.create_conversation(
            db,
            user=current_user,
            title=payload.title,
        )
    )


@router.get("/{conversation_id}/messages", response_model=list[ConversationMessageSummary])
def list_conversation_messages(
    conversation_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> list[ConversationMessageSummary]:
    try:
        messages = conversation_service.list_messages(
            db,
            user=current_user,
            conversation_id=conversation_id,
        )
    except conversation_service.ConversationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return [_message(message) for message in messages]


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_conversation(
    conversation_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> Response:
    try:
        conversation_service.delete_conversation(
            db,
            user=current_user,
            conversation_id=conversation_id,
        )
    except conversation_service.ConversationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
