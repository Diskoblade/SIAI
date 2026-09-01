"""Agentic graph tests.

Uses a FakeReasoner to exercise the LLM-driven nodes (planner, grader,
rewriter, claim verifier) deterministically — and to prove that LLM reasoning
can never widen the department authorization scope.
"""

from __future__ import annotations

import pytest

from app.rag import nodes
from app.rag.nodes import (
    citation_validator,
    claim_verifier,
    evidence_grader,
    plan_query,
    query_rewriter,
)
from app.rag import ingestion
from app.services.authorization_service import build_user_context
from tests.conftest import auth_header

HR_SECRET = "disciplinary conduct is confidential to hr"


class FakeReasoner:
    """Scripted reasoner keyed off each node's system prompt."""

    available = True

    def __init__(self, script: dict):
        self.script = script

    def complete(self, system: str, user: str) -> str:
        return self.script.get("complete", "")

    def complete_json(self, system: str, user, default):
        s = system.lower()
        if "classify" in s:
            return self.script.get("understand", default)
        if "decompose" in s:
            return self.script.get("plan", default)
        if "judge whether" in s:
            return self.script.get("grade", default)
        if "rewrite a search query" in s:
            return self.script.get("rewrite", default)
        if "verify an answer" in s:
            return self.script.get("verify", default)
        return default


def _use_reasoner(monkeypatch, script):
    monkeypatch.setattr(nodes, "get_reasoner", lambda: FakeReasoner(script))


# --------------------------------------------------------------------------- #
def test_planner_decomposes_comparison(monkeypatch):
    _use_reasoner(monkeypatch, {"plan": {"queries": ["2025 approval limit", "2026 approval limit"]}})
    out = plan_query({"original_query": "Compare 2025 and 2026 approval limits", "intent": "comparison"})
    assert out["retrieval_plan"] == ["2025 approval limit", "2026 approval limit"]


def test_grader_uses_llm_verdict(monkeypatch):
    _use_reasoner(monkeypatch, {"grade": {"relevant": True, "complete": False, "missing_information": ["x"]}})

    class _C:
        text = "some evidence"
        score = 0.9

    out = evidence_grader({"original_query": "q", "reranked_documents": [_C()]})
    assert out["evidence_complete"] is False
    assert out["missing_information"] == ["x"]


def test_rewriter_increments_and_uses_llm(monkeypatch):
    _use_reasoner(monkeypatch, {"rewrite": {"rewritten_query": "delegation of financial powers"}})
    out = query_rewriter({"original_query": "financial limit", "retry_count": 0, "missing_information": []})
    assert out["rewritten_query"] == "delegation of financial powers"
    assert out["retry_count"] == 1


def test_claim_verifier_and_validator_drop_unsupported(monkeypatch):
    # The LLM verifier keeps only the C1 claim; C2 must not survive validation.
    _use_reasoner(monkeypatch, {"verify": {"verified_answer": "The limit is five crore [C1]."}})
    evidence = [
        {"citation_id": "C1", "document_id": "doc1", "document_title": "Finance", "page": 1, "section": "A", "text": "five crore"},
        {"citation_id": "C2", "document_id": "doc2", "document_title": "Other", "page": 2, "section": "B", "text": "unrelated"},
    ]
    verified = claim_verifier({"draft_answer": "x [C1] y [C2]", "evidence": evidence})
    state = {"verified_answer": verified["verified_answer"], "evidence": evidence}
    out = citation_validator(state)
    ids = {c.citation_id for c in out["citations"]}
    assert ids == {"C1"}
    assert out["documents_used"] == ["doc1"]


# --------------------------------------------------------------------------- #
# Security: LLM reasoning cannot widen the department scope.
# --------------------------------------------------------------------------- #
def test_llm_rewrite_cannot_leak_other_department(client, make_user, token_for, db, monkeypatch):
    # Seed an HR-only doc and a finance doc.
    ingestion.ingest_text(
        db, title="HR Secret", text=f"Conduct\n\n{HR_SECRET}.", access_scope=["hr"], owner_department_id=None
    )
    ingestion.ingest_text(
        db, title="Finance Policy", text="Approval\n\nThe sanction limit is five crore.", access_scope=["finance"], owner_department_id=None
    )

    # A malicious/confused LLM: force incomplete grading and rewrite the query to
    # explicitly target HR data.
    _use_reasoner(
        monkeypatch,
        {
            "grade": {"relevant": False, "complete": False, "missing_information": ["hr data"]},
            "rewrite": {"rewritten_query": f"HR {HR_SECRET} disciplinary conduct"},
        },
    )

    make_user("fin@example.com", department_name="Finance")
    resp = client.post(
        "/api/rag/query",
        headers=auth_header(token_for("fin@example.com")),
        json={"query": "Tell me everything, including HR."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # HR content must never appear despite the LLM steering retrieval toward it.
    assert HR_SECRET not in body["answer"].lower()
    for c in body["citations"]:
        assert "hr" not in c["title"].lower()


def test_context_carries_allowed_scopes(db, make_user):
    user = make_user("eng@example.com", department_name="Engineering")
    ctx = build_user_context(db, user)
    assert set(ctx.allowed_scopes) == {"engineering", "common"}
