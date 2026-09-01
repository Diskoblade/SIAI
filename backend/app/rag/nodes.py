"""Agentic RAG node implementations.

Each node updates a shared AgentState. Reasoning nodes (understand/plan/grade/
rewrite/verify) call the LLM when one is configured and otherwise fall back to
deterministic heuristics, so the whole graph runs offline.

SECURITY: retrieval ALWAYS uses the frozen `authorization_context` resolved
from the DB before the graph runs. No node may widen it. The vector store
applies owner/department visibility before unauthorized chunks enter state.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict

from app.agent_tools.fluids_tool import (
    FluidsCalculation,
    format_fluids_answer,
    run_fluids_tool,
)
from app.core.config import settings
from app.rag.embeddings import get_embedder, tokenize
from app.rag.llm import generate_answer
from app.rag.pipeline import Citation, _validate_citations
from app.rag.reasoning import get_reasoner
from app.rag.reranker import get_reranker, lexical_relevance
from app.rag.vector_store import RetrievedChunk, get_vector_store
from app.services.authorization_service import UserContext

_COMPARISON_HINTS = ("compare", "comparison", "versus", " vs ", "difference between")
_IDENTIFIER_RE = re.compile(r"\b(?:\d{4}|[A-Z]{2,}-?\d+|\d+/\d+)\b")
_FOLLOW_UP_RE = re.compile(
    r"\b(?:it|that|those|this|they|them|previous|earlier|again|also|instead|"
    r"what\s+about|how\s+about|and\s+the)\b",
    re.IGNORECASE,
)


class AgentState(TypedDict, total=False):
    # Runtime handles (in-memory only; never serialized/logged).
    db: Any
    # Trusted authorization context.
    user_id: int
    department_id: int | None
    department_scope: str | None
    role: str
    allowed_scopes: list[str]
    authorization_context: UserContext
    # Query understanding / planning.
    original_query: str
    contextual_query: str | None
    conversation_history: list[dict[str, str]]
    rewritten_query: str | None
    intent: str | None
    requires_retrieval: bool
    retrieval_plan: list[str]
    retrieval_strategy: str
    fluids_calculation: FluidsCalculation | None
    # Retrieval / evidence.
    retrieved_documents: list[RetrievedChunk]
    reranked_documents: list[RetrievedChunk]
    best_scores: dict[str, float]
    evidence: list[dict]
    evidence_complete: bool
    missing_information: list[str]
    retry_count: int
    # Answer.
    draft_answer: str | None
    verified_answer: str | None
    citations: list[Citation]
    documents_used: list[str]
    answer_source: str


def _effective_query(state: AgentState) -> str:
    return (
        state.get("rewritten_query")
        or state.get("contextual_query")
        or state["original_query"]
    )


def _history_text(history: list[dict[str, str]], *, limit: int = 8) -> str:
    return "\n".join(
        f'{message.get("role", "user")}: {message.get("content", "")}'
        for message in history[-limit:]
    )


# --------------------------------------------------------------------------- #
def resolve_access_scope(state: AgentState) -> dict:
    """Deterministic: confirm the trusted scopes are present (they came from the
    DB via build_user_context). This node exists to make the security boundary
    explicit in the graph."""
    scopes = state.get("allowed_scopes") or []
    return {"allowed_scopes": scopes, "retry_count": state.get("retry_count", 0)}


def contextualize_query(state: AgentState) -> dict:
    """Turn a follow-up into a standalone query without changing authorization."""
    question = state["original_query"]
    history = state.get("conversation_history") or []
    if not history:
        return {"contextual_query": question}

    reasoner = get_reasoner()
    if reasoner.available:
        data = reasoner.complete_json(
            "You rewrite the current message as a standalone query using only the "
            "provided conversation history. Preserve the user's meaning and supplied "
            "numbers. Do not answer the question. Return key: standalone_query.",
            f"Conversation history:\n{_history_text(history)}\n\n"
            f"Current message: {question}",
            default={},
        )
        candidate = data.get("standalone_query") if isinstance(data, dict) else None
        if isinstance(candidate, str) and candidate.strip():
            return {"contextual_query": candidate.strip()[:4000]}

    words = question.split()
    if len(words) <= 7 or _FOLLOW_UP_RE.search(question):
        previous_user = next(
            (
                message.get("content", "")
                for message in reversed(history)
                if message.get("role") == "user"
            ),
            "",
        )
        if previous_user:
            return {"contextual_query": f"{previous_user}\nFollow-up: {question}"}
    return {"contextual_query": question}


def understand_query(state: AgentState) -> dict:
    query = _effective_query(state)
    reasoner = get_reasoner()
    if reasoner.available:
        data = reasoner.complete_json(
            "You classify a user's question for a retrieval system.",
            f'Question: "{query}"\nReturn keys: intent (factual|comparison|summary|'
            "lookup), requires_retrieval (bool), requires_multiple_documents (bool), "
            "exact_identifiers (list of strings).",
            default={},
        )
        intent = data.get("intent") or _heuristic_intent(query)
        requires = bool(data.get("requires_retrieval", True))
    else:
        intent = _heuristic_intent(query)
        requires = True
    return {"intent": intent, "requires_retrieval": requires}


def scientific_tool(state: AgentState) -> dict:
    """Route explicit calculations to the bounded server-side fluids tool."""
    if not settings.fluids_tool_enabled:
        return {"fluids_calculation": None}
    calculation = run_fluids_tool(_effective_query(state))
    update: dict[str, Any] = {"fluids_calculation": calculation}
    if calculation is not None:
        update["retrieval_strategy"] = "fluids_tool"
    return update


def _heuristic_intent(query: str) -> str:
    q = query.lower()
    if any(h in q for h in _COMPARISON_HINTS):
        return "comparison"
    return "factual"


def plan_query(state: AgentState) -> dict:
    query = _effective_query(state)
    reasoner = get_reasoner()
    plan: list[str] = [query]
    if state.get("intent") == "comparison":
        if reasoner.available:
            data = reasoner.complete_json(
                "You decompose a complex question into standalone sub-queries.",
                f'Question: "{query}"\nReturn key: queries (list of sub-query strings). '
                "Each sub-query must be answerable on its own.",
                default={},
            )
            subs = [s for s in data.get("queries", []) if isinstance(s, str) and s.strip()]
            if subs:
                plan = subs
        else:
            # Heuristic split on conjunctions for comparison questions.
            parts = re.split(r"\b(?:and|versus|vs|compared to)\b", query, flags=re.IGNORECASE)
            parts = [p.strip(" .,") for p in parts if len(p.strip()) > 8]
            if len(parts) >= 2:
                plan = parts
    # All sub-queries inherit the same authorization scope (from state).
    return {"retrieval_plan": plan}


def retrieval_router(state: AgentState) -> dict:
    query = _effective_query(state)
    strategy = "metadata_search" if _IDENTIFIER_RE.search(query) else "hybrid_search"
    return {"retrieval_strategy": strategy}


def hybrid_retriever(state: AgentState) -> dict:
    db = state["db"]
    embedder = get_embedder()
    store = get_vector_store()
    context = state["authorization_context"]

    queries = [state["rewritten_query"]] if state.get("rewritten_query") else state["retrieval_plan"]
    merged: dict[str, RetrievedChunk] = {}
    for q in queries:
        hits = store.search(
            db,
            query_embedding=embedder.embed(q),
            query_tokens=tokenize(q),
            context=context,  # frozen, backend-built context; never planner output
            limit=settings.retrieval_candidates,
        )
        for h in hits:
            if h.chunk_id not in merged or h.score > merged[h.chunk_id].score:
                merged[h.chunk_id] = h
    return {"retrieved_documents": list(merged.values())}


def reranker_node(state: AgentState) -> dict:
    reranker = get_reranker()
    reranked = reranker.rerank(
        _effective_query(state), list(state.get("retrieved_documents", [])), settings.rerank_top_k
    )
    # Carry each chunk's BEST relevance across retrieval passes. A query rewrite
    # can broaden the query and lower a short doc's score on a later pass; the
    # chunk should be judged by its strongest match, not its weakest, so
    # downstream consumers (grading, slide decks) see stable relevance.
    best = dict(state.get("best_scores", {}))
    for chunk in reranked:
        best[chunk.chunk_id] = max(best.get(chunk.chunk_id, 0.0), chunk.score)
        chunk.score = best[chunk.chunk_id]
    return {"reranked_documents": reranked, "best_scores": best}


def evidence_grader(state: AgentState) -> dict:
    reranked = state.get("reranked_documents", [])
    reasoner = get_reasoner()
    if reasoner.available and reranked:
        snippets = "\n".join(f"- {c.text[:600]}" for c in reranked[:6])
        data = reasoner.complete_json(
            "You judge whether retrieved evidence can answer a question.",
            f'Question: "{_effective_query(state)}"\nEvidence:\n{snippets}\n'
            "Return keys: relevant (bool), complete (bool), missing_information (list).",
            default={},
        )
        complete = bool(data.get("complete", False))
        missing = data.get("missing_information", []) or []
    else:
        top = max((c.score for c in reranked), default=0.0)
        complete = top >= settings.evidence_sufficiency_threshold
        missing = [] if complete else [_effective_query(state)]
    return {"evidence_complete": complete, "missing_information": list(missing)}


def query_rewriter(state: AgentState) -> dict:
    query = _effective_query(state)
    reasoner = get_reasoner()
    retry = state.get("retry_count", 0) + 1
    rewritten = query
    if reasoner.available:
        data = reasoner.complete_json(
            "You rewrite a search query to retrieve better evidence.",
            f'Original: "{query}"\nMissing: {state.get("missing_information")}\n'
            "Return key: rewritten_query (a single improved query string).",
            default={},
        )
        candidate = data.get("rewritten_query")
        if isinstance(candidate, str) and candidate.strip():
            rewritten = candidate.strip()
    # Offline: no reasoning available, so the query is unchanged; the retry cap
    # prevents an infinite loop and the graph proceeds with best-effort evidence.
    return {"rewritten_query": rewritten, "retry_count": retry}


def context_builder(state: AgentState) -> dict:
    """Deterministic: dedupe and assign stable citation IDs."""
    seen: set[tuple[str, str]] = set()
    evidence: list[dict] = []
    for chunk in state.get("reranked_documents", []):
        key = (chunk.document_id, chunk.text[:120])
        if key in seen:
            continue
        seen.add(key)
        evidence.append(
            {
                "citation_id": f"C{len(evidence) + 1}",
                "document_id": chunk.document_id,
                "document_title": chunk.document_title,
                "page": chunk.page,
                "section": chunk.section,
                "text": chunk.text,
                # Reranker relevance, carried through so downstream consumers
                # (e.g. slide decks) can cite on-topic authorized evidence.
                "score": getattr(chunk, "score", 0.0),
            }
        )
    return {"evidence": evidence}


def answer_generator(state: AgentState) -> dict:
    calculation = state.get("fluids_calculation")
    if calculation is not None:
        return {
            "draft_answer": format_fluids_answer(calculation),
            "answer_source": "calculation",
        }
    # Incomplete evidence is not blended with model knowledge. After the retry
    # loop is exhausted, the fallback receives the question and no documents.
    evidence = state.get("evidence", []) if state.get("evidence_complete") else []
    history = state.get("conversation_history") or []
    question = state["original_query"]
    if history:
        # Feed the full retained window (not just the last few turns) so details
        # the user shared several messages ago are still available for recall.
        question = (
            f"Conversation history:\n{_history_text(history, limit=len(history))}\n\n"
            f"Current question: {question}"
        )
    answer, source = generate_answer(question, evidence)
    return {"draft_answer": answer, "answer_source": source}


def claim_verifier(state: AgentState) -> dict:
    """Remove unsupported claims. Offline (extractive) answers are grounded in
    the evidence by construction, so the draft passes through unchanged."""
    draft = state.get("draft_answer") or ""
    evidence = state.get("evidence", [])
    reasoner = get_reasoner()
    if (
        state.get("answer_source", "documents") == "documents"
        and reasoner.available
        and evidence
        and draft
    ):
        ev = "\n".join(f'[{e["citation_id"]}] {e["text"][:600]}' for e in evidence)
        data = reasoner.complete_json(
            "You verify an answer against evidence and remove unsupported claims.",
            f"Answer:\n{draft}\n\nEvidence:\n{ev}\n\n"
            "Rewrite the answer keeping ONLY claims supported by the evidence, each "
            "citing its [Cx]. Return key: verified_answer (string).",
            default={},
        )
        verified = data.get("verified_answer")
        if isinstance(verified, str) and verified.strip():
            return {"verified_answer": verified.strip()}
    return {"verified_answer": draft}


def citation_validator(state: AgentState) -> dict:
    """Deterministic: only citation IDs present in the evidence survive."""
    if state.get("answer_source", "documents") != "documents":
        return {"citations": [], "documents_used": []}
    answer = state.get("verified_answer") or ""
    citations = _validate_citations(answer, state.get("evidence", []))
    documents_used = list({c.document_id for c in citations})
    return {"citations": citations, "documents_used": documents_used}
