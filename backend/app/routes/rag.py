"""Protected RAG route.

The endpoint accepts a question and an optional owner-checked conversation ID.
Authorized scopes/collection are derived server-side from the authenticated
user's department — never from the request body, query string, or headers.
Retrieval is restricted to authorized chunks before anything reaches the model.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import CurrentUser
from app.database import get_db
from app.models.audit import RagAuditLog
from app.memory.service import capture_message
from app.rag.graph import run_agentic_query
from app.media.deck import build_deck_visual_slides
from app.rag.llm import generate_general_knowledge_slides
from app.rag.presentation import (
    build_presentation_spec,
    content_slide_budget,
    detect_requested_visuals,
    is_slide_request,
    presentation_topic,
)
from app.schemas.rag import (
    Citation,
    RagHistoryItem,
    RagQueryRequest,
    RagQueryResponse,
    RagStatus,
    ScientificCalculation,
)
from app.services.authorization_service import (
    NotAuthorizedError,
    build_user_context,
    get_authorized_vector_collection,
)
from app.services import conversation_service, report_service

router = APIRouter(prefix="/api/rag", tags=["rag"])
logger = logging.getLogger(__name__)

DbSession = Annotated[Session, Depends(get_db)]


@router.post("/query", response_model=RagQueryResponse, response_model_exclude_none=True)
def query(payload: RagQueryRequest, current_user: CurrentUser, db: DbSession) -> RagQueryResponse:
    conversation = None
    conversation_history: list[dict[str, str]] = []
    if payload.conversation_id is not None:
        try:
            conversation = conversation_service.get_conversation(
                db,
                user=current_user,
                conversation_id=payload.conversation_id,
            )
            conversation_history = conversation_service.history_for_agent(
                db,
                user=current_user,
                conversation_id=payload.conversation_id,
            )
        except conversation_service.ConversationNotFoundError:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )

    # Report / Approval Note intent: if the user asks for a report, follow the
    # Approval Note workflow — ask for (or pre-fill) the details and let them
    # generate the document (which opens in ONLYOFFICE). Short-circuits the RAG
    # answer since the user wants a document, not a Q&A response.
    if report_service.detect_report_intent(payload.question):
        report = report_service.build_report_suggestion(db, current_user, payload.question)
        response = RagQueryResponse(
            question=payload.question,
            answer=report.prompt,
            answer_source="general_knowledge",
            report=report,
            conversation_id=conversation.id if conversation is not None else None,
            conversation_title=conversation.title if conversation is not None else None,
        )
        try:
            capture_message(db, user=current_user, message=payload.question)
        except Exception:  # noqa: BLE001
            logger.exception("Private conversation memory capture failed.")
        if conversation is not None:
            conversation = conversation_service.add_turn(
                db,
                user=current_user,
                conversation_id=conversation.id,
                question=payload.question,
                response=response.model_dump(mode="json", exclude_none=True),
            )
            response.conversation_title = conversation.title
        return response

    # Trusted, backend-built authorization context (identity + allowed scopes).
    context = build_user_context(db, current_user)

    # For a slide request, retrieve on the underlying topic (not the
    # "create a deck about …" boilerplate) so authorized departmental documents
    # actually match. Authorization is unchanged — retrieval still runs only
    # within the user's allowed scopes.
    retrieval_question = payload.question
    if is_slide_request(payload.question):
        topic = presentation_topic(payload.question)
        if topic:
            retrieval_question = topic

    # Agentic LangGraph pipeline (retrieval stays restricted to the context's
    # authorized scopes at every node).
    result = run_agentic_query(
        db,
        context=context,
        question=retrieval_question,
        conversation_history=conversation_history,
    )

    # Best-effort primary collection label (backward-compatible field).
    try:
        collection = get_authorized_vector_collection(db, current_user)
    except NotAuthorizedError:
        collection = None

    # For a general-knowledge slide request, ask the LLM for a complete,
    # structured deck outline so the slides carry full content (not a truncated
    # prose fragment). Authorized-document decks keep their cited evidence.
    gk_outline = None
    media_slides = None
    if is_slide_request(payload.question):
        topic = presentation_topic(payload.question) or payload.question
        if result.answer_source == "general_knowledge":
            gk_outline = generate_general_knowledge_slides(
                topic, content_slide_budget(payload.question)
            )
        # Rendered charts / diagrams / data tables (DuckDB + Vega-Lite + Mermaid).
        # Pass evidence only for a document-grounded answer; for a general-
        # knowledge deck the retrieved-but-rejected chunks are off-topic and
        # would derail the visual generator, so visuals come from the topic.
        evidence_text = ""
        if result.answer_source == "documents":
            evidence_text = "\n".join(
                str(e.get("text", "")) for e in (result.evidence or [])
            )[:2000]
        requested_visuals = detect_requested_visuals(payload.question)
        try:
            media_slides = build_deck_visual_slides(
                topic, evidence_text, requested=requested_visuals
            )
        except Exception:  # noqa: BLE001 - visuals are best-effort
            logger.exception("Deck visual generation failed")
            media_slides = None

    # Save only explicit decisions, notes, and preferences. Memory capture is
    # best-effort and must never prevent the current answer from returning.
    try:
        capture_message(db, user=current_user, message=payload.question)
    except Exception:  # noqa: BLE001
        logger.exception("Private conversation memory capture failed.")

    response = RagQueryResponse(
        question=result.question,
        answer=result.answer,
        citations=[
            Citation(
                citation_id=c.citation_id,
                document_id=c.document_id,
                title=c.title,
                page=c.page,
                section=c.section,
            )
            for c in result.citations
        ],
        evidence_status=result.evidence_status,
        documents_used=result.documents_used,
        answer_source=result.answer_source,
        authorized_collection=collection,
        presentation=build_presentation_spec(
            payload.question, result, gk_outline=gk_outline, media_slides=media_slides
        ),
        calculation=(
            ScientificCalculation.model_validate(result.calculation)
            if result.calculation is not None
            else None
        ),
        conversation_id=conversation.id if conversation is not None else None,
        conversation_title=conversation.title if conversation is not None else None,
    )
    if conversation is not None:
        conversation = conversation_service.add_turn(
            db,
            user=current_user,
            conversation_id=conversation.id,
            question=payload.question,
            response=response.model_dump(mode="json", exclude_none=True),
        )
        response.conversation_title = conversation.title
    return response


@router.get("/history", response_model=list[RagHistoryItem])
def history(
    current_user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
) -> list[RagHistoryItem]:
    """Return the CURRENT user's own recent queries (never other users')."""
    rows = db.scalars(
        select(RagAuditLog)
        .where(RagAuditLog.user_id == current_user.id)
        .order_by(RagAuditLog.created_at.desc())
        .limit(limit)
    ).all()
    return [
        RagHistoryItem(
            id=r.id,
            question=r.question,
            retrieval_strategy=r.retrieval_strategy,
            documents_count=len(r.document_ids_accessed or []),
            response_status=r.response_status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/status", response_model=RagStatus)
def status(current_user: CurrentUser) -> RagStatus:
    """Report which providers are active (so the UI can show ChatGPT vs offline).

    Never returns API keys — only whether one is configured.
    """
    llm_configured = settings.llm_provider == "openai" and bool(settings.llm_api_key)
    mode = "ChatGPT / OpenAI" if llm_configured else "Offline (local heuristics)"
    return RagStatus(
        mode=mode,
        llm_provider=settings.llm_provider,
        embedding_provider=settings.embedding_provider,
        vector_store=settings.vector_store,
        reranker_provider=settings.reranker_provider,
        llm_configured=llm_configured,
        general_knowledge_fallback_enabled=settings.rag_general_knowledge_fallback_enabled,
        fluids_tool_enabled=settings.fluids_tool_enabled,
    )
