"""RAG query schemas.

The request accepts the user's question (aliased as `query` per the RAG spec, or
`question` for backward compatibility) and an optional private conversation ID.
It never accepts a department or collection name — the backend derives all
authorization from the authenticated user. `extra="forbid"` rejects any
smuggled authorization field.
"""

from __future__ import annotations

from datetime import datetime

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

MAX_RAG_QUERY_LENGTH = 10_000


class RagQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

    question: str = Field(
        min_length=1,
        max_length=MAX_RAG_QUERY_LENGTH,
        validation_alias=AliasChoices("question", "query"),
    )
    conversation_id: str | None = Field(default=None, min_length=36, max_length=36)


class Citation(BaseModel):
    citation_id: str
    document_id: str
    title: str
    page: int | None = None
    section: str | None = None


class PresentationTable(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class PresentationSlide(BaseModel):
    layout: Literal["summary", "evidence", "sources", "notice", "chart", "diagram", "table"]
    title: str = Field(min_length=1, max_length=120)
    bullets: list[str] = Field(default_factory=list, max_length=6)
    source_ids: list[str] = Field(default_factory=list)
    # Rendered visual (chart/diagram) as a base64-encoded PNG, embedded on the
    # slide by the frontend. Data tables travel in `table`.
    image_base64: str | None = None
    image_alt: str | None = None
    table: PresentationTable | None = None


class PresentationSpec(BaseModel):
    kind: Literal["pptx"] = "pptx"
    filename: str
    title: str
    subtitle: str
    slide_count: int = Field(ge=2, le=24)
    slides: list[PresentationSlide]
    source_mode: Literal["documents", "general_knowledge", "unavailable"] = "documents"


class CalculationValue(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    value: float
    unit: str = ""


class ScientificCalculation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tool: Literal["fluids"] = "fluids"
    library_version: str
    operation: str
    title: str
    success: bool
    inputs: list[CalculationValue] = Field(default_factory=list)
    outputs: list[CalculationValue] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    error: str | None = None


class ReportTypeOption(BaseModel):
    id: int
    name: str


class ApprovalNoteReport(BaseModel):
    """Attached to a chat reply when the user asks for a report/approval note.

    The frontend renders it as a "Create Approval Note" card: the type may be
    pre-matched and the title/parameters pre-filled from the request, and the
    user confirms and generates the document (which then opens in ONLYOFFICE).
    """

    status: Literal["ready", "needs_details", "unavailable"] = "needs_details"
    prompt: str
    available_types: list[ReportTypeOption] = Field(default_factory=list)
    matched_type_id: int | None = None
    matched_type_name: str | None = None
    suggested_title: str | None = None
    suggested_parameters: dict[str, str] = Field(default_factory=dict)
    letterhead_ready: bool = True


class RagQueryResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    evidence_status: str = "insufficient"
    documents_used: list[str] = Field(default_factory=list)
    answer_source: Literal["documents", "general_knowledge", "calculation", "unavailable"] = "documents"
    # Retained from the auth milestone for backward compatibility / demo clarity.
    authorized_collection: str | None = None
    presentation: PresentationSpec | None = None
    calculation: ScientificCalculation | None = None
    report: ApprovalNoteReport | None = None
    conversation_id: str | None = None
    conversation_title: str | None = None


class RagHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question: str
    retrieval_strategy: str
    documents_count: int
    response_status: str
    created_at: datetime


class RagStatus(BaseModel):
    mode: str
    llm_provider: str
    embedding_provider: str
    vector_store: str
    reranker_provider: str
    llm_configured: bool
    general_knowledge_fallback_enabled: bool
    fluids_tool_enabled: bool
