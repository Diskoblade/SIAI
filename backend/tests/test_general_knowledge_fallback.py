"""General-knowledge fallback behavior and provenance tests."""

from __future__ import annotations

from app.rag import llm
from tests.conftest import auth_header


class _FakeKnowledgeAnswerer:
    supports_general_knowledge = True

    def generate(self, question: str, evidence: list[dict]) -> str:
        return "Grounded answer [C1]"

    def generate_general_knowledge(self, question: str) -> str:
        return "General knowledge answer about photosynthesis."


def test_generate_answer_prefers_document_evidence(monkeypatch):
    monkeypatch.setattr(llm, "_answerer", _FakeKnowledgeAnswerer())

    answer, source = llm.generate_answer("question", [{"citation_id": "C1"}])

    assert answer == "Grounded answer [C1]"
    assert source == "documents"


def test_generate_answer_falls_back_without_evidence(monkeypatch):
    monkeypatch.setattr(llm, "_answerer", _FakeKnowledgeAnswerer())

    answer, source = llm.generate_answer("What is photosynthesis?", [])

    assert answer == "General knowledge answer about photosynthesis."
    assert source == "general_knowledge"


def test_rag_route_returns_uncited_general_knowledge(
    client, make_user, token_for, monkeypatch
):
    make_user("fallback@example.com")
    monkeypatch.setattr(llm, "_answerer", _FakeKnowledgeAnswerer())

    response = client.post(
        "/api/rag/query",
        headers=auth_header(token_for("fallback@example.com")),
        json={"question": "What is photosynthesis?"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_source"] == "general_knowledge"
    assert body["answer"] == "General knowledge answer about photosynthesis."
    assert body["citations"] == []
    assert body["documents_used"] == []
    assert body["evidence_status"] == "insufficient"


def test_rag_route_accepts_very_long_questions(client, make_user, token_for, monkeypatch):
    make_user("long-query@example.com")
    monkeypatch.setattr(llm, "_answerer", _FakeKnowledgeAnswerer())

    response = client.post(
        "/api/rag/query",
        headers=auth_header(token_for("long-query@example.com")),
        json={"question": "Q" * 10_000},
    )

    assert response.status_code == 200, response.text
