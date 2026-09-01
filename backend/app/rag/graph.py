"""LangGraph agentic RAG graph (spec #11, #22).

    START -> resolve_access_scope -> contextualize_query -> understand_query -> plan_query
          -> retrieval_router -> hybrid_retriever -> reranker -> evidence_grader
          -> (insufficient & retries left) -> query_rewriter -> hybrid_retriever
          -> (sufficient or retries exhausted) -> context_builder
          -> answer_generator -> claim_verifier -> citation_validator -> END

The authorization context is carried in the state for the entire run, and every
retrieval call uses those scopes. The rewrite loop is retry-capped so it can
never run unbounded.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.core.config import settings
from app.rag import nodes
from app.rag.nodes import AgentState
from app.rag.pipeline import RagResult, _write_audit
from app.services.authorization_service import UserContext


def _route_after_grader(state: AgentState) -> str:
    """Loop back to rewriting while evidence is insufficient and retries remain."""
    if state.get("evidence_complete"):
        return "sufficient"
    if state.get("retry_count", 0) >= settings.max_retrieval_retries:
        return "sufficient"  # give up gracefully; proceed with best-effort evidence
    return "rewrite"


def _route_after_scientific_tool(state: AgentState) -> str:
    return "calculated" if state.get("fluids_calculation") is not None else "retrieve"


def _build_graph():
    g = StateGraph(AgentState)

    g.add_node("resolve_access_scope", nodes.resolve_access_scope)
    g.add_node("contextualize_query", nodes.contextualize_query)
    g.add_node("understand_query", nodes.understand_query)
    g.add_node("scientific_tool", nodes.scientific_tool)
    g.add_node("plan_query", nodes.plan_query)
    g.add_node("retrieval_router", nodes.retrieval_router)
    g.add_node("hybrid_retriever", nodes.hybrid_retriever)
    g.add_node("reranker", nodes.reranker_node)
    g.add_node("evidence_grader", nodes.evidence_grader)
    g.add_node("query_rewriter", nodes.query_rewriter)
    g.add_node("context_builder", nodes.context_builder)
    g.add_node("answer_generator", nodes.answer_generator)
    g.add_node("claim_verifier", nodes.claim_verifier)
    g.add_node("citation_validator", nodes.citation_validator)

    g.add_edge(START, "resolve_access_scope")
    g.add_edge("resolve_access_scope", "contextualize_query")
    g.add_edge("contextualize_query", "understand_query")
    g.add_edge("understand_query", "scientific_tool")
    g.add_conditional_edges(
        "scientific_tool",
        _route_after_scientific_tool,
        {"calculated": "answer_generator", "retrieve": "plan_query"},
    )
    g.add_edge("plan_query", "retrieval_router")
    g.add_edge("retrieval_router", "hybrid_retriever")
    g.add_edge("hybrid_retriever", "reranker")
    g.add_edge("reranker", "evidence_grader")
    g.add_conditional_edges(
        "evidence_grader",
        _route_after_grader,
        {"rewrite": "query_rewriter", "sufficient": "context_builder"},
    )
    g.add_edge("query_rewriter", "hybrid_retriever")
    g.add_edge("context_builder", "answer_generator")
    g.add_edge("answer_generator", "claim_verifier")
    g.add_edge("claim_verifier", "citation_validator")
    g.add_edge("citation_validator", END)

    return g.compile()


# Compiled once and reused (stateless across requests; per-request state is
# passed into invoke()).
_compiled = None


def get_compiled_graph():
    global _compiled
    if _compiled is None:
        _compiled = _build_graph()
    return _compiled


def reset_graph() -> None:
    global _compiled
    _compiled = None


def run_agentic_query(
    db: Session,
    *,
    context: UserContext,
    question: str,
    conversation_history: list[dict[str, str]] | None = None,
) -> RagResult:
    """Execute the agentic graph for one authorized question and audit it."""
    initial: AgentState = {
        "db": db,
        "user_id": context.user_id,
        "department_id": context.department_id,
        "department_scope": context.department_scope,
        "role": context.role,
        "allowed_scopes": list(context.allowed_scopes),
        "authorization_context": context,
        "original_query": question,
        "contextual_query": None,
        "conversation_history": list(conversation_history or []),
        "rewritten_query": None,
        "retry_count": 0,
    }

    final = get_compiled_graph().invoke(initial)

    evidence = final.get("evidence", [])
    complete = final.get("evidence_complete", False)
    answer_source = final.get("answer_source", "unavailable")
    calculation = final.get("fluids_calculation")
    if answer_source == "calculation" and calculation and calculation.success:
        status = "sufficient"
    elif answer_source == "documents" and evidence and complete:
        status = "sufficient"
    elif answer_source == "documents" and evidence:
        status = "partial"
    else:
        status = "insufficient"

    result = RagResult(
        question=question,
        answer=final.get("verified_answer") or final.get("draft_answer") or "",
        citations=final.get("citations", []),
        evidence_status=status,
        documents_used=final.get("documents_used", []),
        retrieval_strategy=final.get("retrieval_strategy", "hybrid_search"),
        retrieval_retry_count=final.get("retry_count", 0),
        evidence=evidence,
        answer_source=answer_source,
        calculation=calculation,
    )
    _write_audit(db, context, result, accessed=[e["document_id"] for e in evidence])
    return result
