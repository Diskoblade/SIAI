"""Persistence and bounded history assembly for private conversations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationMessage, ConversationRole
from app.models.user import User

MAX_CONTEXT_MESSAGES = 12
MAX_CONTEXT_CHARS = 12_000


class ConversationNotFoundError(Exception):
    pass


def _owned_conversation(db: Session, *, user: User, conversation_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise ConversationNotFoundError()
    return conversation


def create_conversation(
    db: Session, *, user: User, title: str | None = None
) -> Conversation:
    conversation = Conversation(
        user_id=user.id,
        title=(title or "New conversation").strip(),
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def list_conversations(db: Session, *, user: User) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
        )
    )


def get_conversation(
    db: Session, *, user: User, conversation_id: str
) -> Conversation:
    return _owned_conversation(db, user=user, conversation_id=conversation_id)


def list_messages(
    db: Session, *, user: User, conversation_id: str
) -> list[ConversationMessage]:
    conversation = _owned_conversation(db, user=user, conversation_id=conversation_id)
    return list(conversation.messages)


def history_for_agent(
    db: Session, *, user: User, conversation_id: str
) -> list[dict[str, str]]:
    """Return newest useful messages within strict count and character limits."""
    conversation = _owned_conversation(db, user=user, conversation_id=conversation_id)
    selected: list[dict[str, str]] = []
    characters = 0
    for message in reversed(conversation.messages[-MAX_CONTEXT_MESSAGES:]):
        remaining = MAX_CONTEXT_CHARS - characters
        if remaining <= 0:
            break
        content = message.content
        if len(content) > remaining:
            content = content[-remaining:]
        selected.append({"role": message.role.value, "content": content})
        characters += len(content)
    selected.reverse()
    return selected


def add_turn(
    db: Session,
    *,
    user: User,
    conversation_id: str,
    question: str,
    response: dict[str, Any],
) -> Conversation:
    conversation = _owned_conversation(db, user=user, conversation_id=conversation_id)
    now = datetime.now(timezone.utc)
    if not conversation.messages and conversation.title == "New conversation":
        conversation.title = _title_from_question(question)
    conversation.updated_at = now
    conversation.messages.extend(
        [
            ConversationMessage(
                role=ConversationRole.USER,
                content=question,
                created_at=now,
            ),
            ConversationMessage(
                role=ConversationRole.ASSISTANT,
                content=str(response.get("answer") or ""),
                answer_source=response.get("answer_source"),
                evidence_status=response.get("evidence_status"),
                citations=list(response.get("citations") or []),
                documents_used=list(response.get("documents_used") or []),
                authorized_collection=response.get("authorized_collection"),
                presentation=response.get("presentation"),
                calculation=response.get("calculation"),
                created_at=now,
            ),
        ]
    )
    db.commit()
    db.refresh(conversation)
    return conversation


def delete_conversation(db: Session, *, user: User, conversation_id: str) -> None:
    conversation = _owned_conversation(db, user=user, conversation_id=conversation_id)
    db.delete(conversation)
    db.commit()


def _title_from_question(question: str) -> str:
    title = " ".join(question.split()).strip()
    if len(title) <= 72:
        return title
    return title[:69].rsplit(" ", 1)[0] + "..."
