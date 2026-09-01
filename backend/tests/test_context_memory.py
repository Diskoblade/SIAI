"""Conversation context memory: earlier details are available to the answerer."""

from __future__ import annotations

from app.rag import nodes
from app.rag.llm import _looks_like_conversation_recall


def test_recall_detection():
    with_history = (
        "Conversation history:\nuser: my budget is 5 crore\n\n"
        "Current question: what is my budget?"
    )
    assert _looks_like_conversation_recall(with_history)

    general = (
        "Conversation history:\nuser: hello\n\nCurrent question: explain photosynthesis"
    )
    assert not _looks_like_conversation_recall(general)

    # No history at all -> not a recall.
    assert not _looks_like_conversation_recall("what is my budget?")


def test_answer_node_feeds_full_history(monkeypatch):
    """The answer node must surface the whole retained window, not just the last
    few turns, so a detail shared several messages ago is still recallable."""
    captured = {}

    def fake_generate_answer(question, evidence):
        captured["question"] = question
        return ("ok", "general_knowledge")

    monkeypatch.setattr(nodes, "generate_answer", fake_generate_answer)

    history = [{"role": "user", "content": f"early-detail-{i}"} for i in range(10)]
    state = {
        "original_query": "what did I say at the start?",
        "conversation_history": history,
        "evidence_complete": False,
    }
    nodes.answer_generator(state)

    assert "Conversation history:" in captured["question"]
    # The oldest detail (index 0) must survive — proves it is not truncated to
    # only the last handful of messages.
    assert "early-detail-0" in captured["question"]
