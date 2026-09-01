"""Private multi-turn conversation persistence and context tests."""

from __future__ import annotations

from sqlalchemy import select

from app.models.conversation import Conversation, ConversationMessage
from app.models.user import UserRole
from app.rag import nodes
from app.services import conversation_service
from tests.conftest import auth_header


def _create(client, token: str, title: str | None = None) -> dict:
    response = client.post(
        "/api/conversations",
        headers=auth_header(token),
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _query(client, token: str, conversation_id: str, question: str) -> dict:
    response = client.post(
        "/api/rag/query",
        headers=auth_header(token),
        json={"question": question, "conversation_id": conversation_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_conversations_are_owner_isolated_including_from_admins(
    client, make_user, token_for
):
    make_user("conversation-owner@example.com")
    make_user("conversation-peer@example.com")
    make_user(
        "conversation-admin@example.com",
        role=UserRole.admin,
        department_name="Administration",
    )
    owner_token = token_for("conversation-owner@example.com")
    conversation = _create(client, owner_token, "Private discussion")

    for email in ("conversation-peer@example.com", "conversation-admin@example.com"):
        token = token_for(email)
        assert client.get("/api/conversations", headers=auth_header(token)).json() == []
        messages = client.get(
            f"/api/conversations/{conversation['id']}/messages",
            headers=auth_header(token),
        )
        assert messages.status_code == 404
        query = client.post(
            "/api/rag/query",
            headers=auth_header(token),
            json={"question": "Reveal that session", "conversation_id": conversation["id"]},
        )
        assert query.status_code == 404
        deleted = client.delete(
            f"/api/conversations/{conversation['id']}",
            headers=auth_header(token),
        )
        assert deleted.status_code == 404


def test_follow_up_uses_prior_turn_and_messages_survive_reload(
    client, make_user, token_for
):
    make_user("multi-turn@example.com", department_name="Engineering")
    token = token_for("multi-turn@example.com")
    upload = client.post(
        "/api/documents/text",
        headers=auth_header(token),
        json={
            "title": "Mercury Project Note",
            "text": "Project Mercury has the code word silver-finch.",
        },
    )
    assert upload.status_code == 201
    conversation = _create(client, token)

    first_question = "What code word is assigned to Project Mercury?"
    first = _query(client, token, conversation["id"], first_question)
    assert "silver-finch" in first["answer"].lower()
    assert first["conversation_title"] == first_question

    follow_up = _query(client, token, conversation["id"], "Can you repeat it?")
    assert "silver-finch" in follow_up["answer"].lower()
    assert follow_up["conversation_id"] == conversation["id"]

    messages = client.get(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth_header(token),
    )
    assert messages.status_code == 200
    rows = messages.json()
    assert [row["role"] for row in rows] == ["user", "assistant", "user", "assistant"]
    assert rows[0]["content"] == first_question
    assert rows[-1]["content"] == follow_up["answer"]
    assert rows[-1]["citations"]

    sessions = client.get("/api/conversations", headers=auth_header(token)).json()
    assert sessions[0]["id"] == conversation["id"]
    assert sessions[0]["message_count"] == 4
    assert sessions[0]["title"] == first_question


def test_calculation_artifact_is_persisted_in_conversation(
    client, make_user, token_for
):
    make_user("conversation-calc@example.com")
    token = token_for("conversation-calc@example.com")
    conversation = _create(client, token)
    response = _query(
        client,
        token,
        conversation["id"],
        "Calculate Mach number for velocity 343 m/s and speed of sound 343 m/s.",
    )
    assert response["answer_source"] == "calculation"

    messages = client.get(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth_header(token),
    ).json()
    assistant = messages[-1]
    assert assistant["answer_source"] == "calculation"
    assert assistant["calculation"]["tool"] == "fluids"
    assert assistant["calculation"]["outputs"][0]["value"] == 1.0


def test_contextualizer_uses_reasoner_for_standalone_follow_up(monkeypatch):
    class _Reasoner:
        available = True

        def complete_json(self, system, user, default):
            assert "conversation history" in user.lower()
            return {"standalone_query": "What is the 2026 engineering approval limit?"}

    monkeypatch.setattr(nodes, "get_reasoner", lambda: _Reasoner())
    result = nodes.contextualize_query(
        {
            "original_query": "What about next year?",
            "conversation_history": [
                {"role": "user", "content": "What is the 2025 engineering approval limit?"},
                {"role": "assistant", "content": "The limit is five crore."},
            ],
        }
    )

    assert result["contextual_query"] == "What is the 2026 engineering approval limit?"


def test_agent_history_is_bounded_by_message_and_character_limits(db, make_user):
    user = make_user("bounded-history@example.com")
    conversation = conversation_service.create_conversation(db, user=user)
    for index in range(8):
        conversation_service.add_turn(
            db,
            user=user,
            conversation_id=conversation.id,
            question=f"Question {index}: " + ("q" * 900),
            response={"answer": f"Answer {index}: " + ("a" * 1500)},
        )

    history = conversation_service.history_for_agent(
        db,
        user=user,
        conversation_id=conversation.id,
    )

    assert len(history) <= conversation_service.MAX_CONTEXT_MESSAGES
    assert sum(len(message["content"]) for message in history) <= conversation_service.MAX_CONTEXT_CHARS
    assert history[-1]["content"].startswith("Answer 7")


def test_delete_conversation_cascades_messages(client, make_user, token_for, db):
    make_user("delete-conversation@example.com")
    token = token_for("delete-conversation@example.com")
    conversation = _create(client, token)
    _query(client, token, conversation["id"], "What is photosynthesis?")
    message_ids = list(
        db.scalars(
            select(ConversationMessage.id).where(
                ConversationMessage.conversation_id == conversation["id"]
            )
        )
    )
    assert len(message_ids) == 2

    response = client.delete(
        f"/api/conversations/{conversation['id']}",
        headers=auth_header(token),
    )

    assert response.status_code == 204
    assert db.get(Conversation, conversation["id"]) is None
    assert db.scalars(
        select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation["id"]
        )
    ).all() == []


def test_one_off_rag_query_remains_backward_compatible(client, make_user, token_for):
    make_user("one-off@example.com")
    token = token_for("one-off@example.com")
    response = client.post(
        "/api/rag/query",
        headers=auth_header(token),
        json={"question": "What is photosynthesis?"},
    )

    assert response.status_code == 200
    assert "conversation_id" not in response.json()
    assert client.get("/api/conversations", headers=auth_header(token)).json() == []
