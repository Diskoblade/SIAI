"""Deterministic RAG pipeline (Milestone 1 backbone).

    context -> embed query -> AUTHORIZED hybrid retrieval -> rerank ->
    context builder (dedupe + citation IDs) -> answer -> citation validation -> audit

The LangGraph agentic layer (query understanding/planner/grader/rewriter/claim
verifier) is a later milestone that will wrap this same authorized-retrieval
core — it will not be allowed to widen the visibility filter.

Security-relevant steps (scope resolution, filtering, citation validation,
audit) are deterministic code, never LLM reasoning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import settings
from app.agent_tools.fluids_tool import FluidsCalculation
from app.models.audit import RagAuditLog
from app.rag.embeddings import get_embedder, tokenize
from app.rag.llm import generate_answer
from app.rag.vector_store import RetrievedChunk, get_vector_store
from app.services.authorization_service import UserContext

_CITATION_RE = re.compile(r"\[(C\d+)\]")


@dataclass
class Citation:
    citation_id: str
    document_id: str
    title: str
    page: int | None
    section: str | None


@dataclass
class RagResult:
    question: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    evidence_status: str = "insufficient"
    documents_used: list[str] = field(default_factory=list)
    retrieval_strategy: str = "hybrid"
    retrieval_retry_count: int = 0
    evidence: list[dict] = field(default_factory=list)
    answer_source: str = "documents"
    calculation: FluidsCalculation | None = None


def _build_context(chunks: list[RetrievedChunk]) -> list[dict]:
    """Dedupe, keep the top-k, and assign stable citation IDs (context builder)."""
    seen: set[tuple[str, str]] = set()
    evidence: list[dict] = []
    for chunk in chunks[: settings.rerank_top_k]:
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
            }
        )
    return evidence


def _validate_citations(answer: str, evidence: list[dict]) -> list[Citation]:
    """Keep only citation IDs that (a) the answer references and (b) exist in the
    evidence. The LLM can never introduce a document/page we did not supply."""
    referenced = set(_CITATION_RE.findall(answer))
    valid: list[Citation] = []
    for e in evidence:
        if e["citation_id"] in referenced:
            valid.append(
                Citation(
                    citation_id=e["citation_id"],
                    document_id=e["document_id"],
                    title=e["document_title"],
                    page=e["page"],
                    section=e["section"],
                )
            )
    return valid


def run_rag_query(
    db: Session,
    *,
    context: UserContext,
    question: str,
    retrieval_strategy: str = "hybrid",
) -> RagResult:
    """Execute one authorized RAG query. `context` is the trusted, backend-built
    authorization context — the pipeline never runs without it."""
    embedder = get_embedder()
    store = get_vector_store()

    query_embedding = embedder.embed(question)
    query_tokens = tokenize(question)

    # AUTHORIZED retrieval only — the store applies visibility internally.
    retrieved = store.search(
        db,
        query_embedding=query_embedding,
        query_tokens=query_tokens,
        context=context,
        limit=settings.retrieval_candidates,
    )

    evidence = _build_context(retrieved)
    answer, answer_source = generate_answer(question, evidence)
    citations = _validate_citations(answer, evidence)

    documents_used = list({c.document_id for c in citations})
    result = RagResult(
        question=question,
        answer=answer,
        citations=citations,
        evidence_status="sufficient" if evidence else "insufficient",
        documents_used=documents_used,
        retrieval_strategy=retrieval_strategy,
        retrieval_retry_count=0,
        evidence=evidence,
        answer_source=answer_source,
    )

    _write_audit(db, context, result, accessed=[e["document_id"] for e in evidence])
    return result


def _write_audit(
    db: Session, context: UserContext, result: RagResult, accessed: list[str]
) -> None:
    """Audit every query. No passwords, JWTs, or secrets are recorded."""
    db.add(
        RagAuditLog(
            user_id=context.user_id,
            department_scope=context.department_scope,
            allowed_scopes=list(context.allowed_scopes),
            question=result.question,
            retrieval_strategy=result.retrieval_strategy,
            document_ids_accessed=list({d for d in accessed if d}),
            retrieval_retry_count=result.retrieval_retry_count,
            response_status=(
                result.evidence_status
                if result.answer_source == "documents"
                else result.answer_source
            ),
        )
    )
    db.commit()
