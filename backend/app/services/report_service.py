"""Report/Approval-Note intent handling for the LLM conversation.

When a user says something like "I need a report" or "prepare a CAPEX approval
note" in chat, we detect the intent and build an ApprovalNoteReport suggestion:
match the Approval Note type, pre-fill a title and parameters from the request
(via the existing local LLM, best-effort), and hand the frontend everything it
needs to confirm and generate the document — which then opens in ONLYOFFICE.

No new AI provider is introduced; this reuses the configured reasoner.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.rag import ApprovalNoteReport, ReportTypeOption
from app.services import approval_note_type_service, template_service

# A creation verb followed (within a short span) by report/approval-note/note,
# or the explicit phrase "approval note". Avoids casual uses like "take notes".
_CREATE_REPORT_RE = re.compile(
    r"\b(?:need|want|create|creating|generate|prepare|preparing|draft|drafting|"
    r"make|produce|write|raise|initiate|issue)\b[^.?!\n]{0,40}?"
    r"\b(?:approval\s+notes?|reports?|notes?)\b",
    re.IGNORECASE,
)
_APPROVAL_NOTE_RE = re.compile(r"\bapproval\s+notes?\b", re.IGNORECASE)

_GENERIC_TYPE_WORDS = {"approval", "note", "notes", "and", "the", "of", "for", "work"}


def detect_report_intent(question: str) -> bool:
    return bool(_CREATE_REPORT_RE.search(question) or _APPROVAL_NOTE_RE.search(question))


def _match_type(question: str, types) -> object | None:
    q = question.lower()
    best = None
    best_score = 0
    for note_type in types:
        name = note_type.name.lower()
        tokens = set(re.findall(r"[a-z]{3,}", name)) - _GENERIC_TYPE_WORDS
        acronyms = re.findall(r"\(([a-z]+)\)", name)
        score = sum(1 for tok in tokens if re.search(rf"\b{re.escape(tok)}", q))
        score += sum(3 for acr in acronyms if re.search(rf"\b{re.escape(acr)}\b", q))
        if score > best_score:
            best_score = score
            best = note_type
    return best if best_score > 0 else None


def _extract_details(question: str, type_name: str | None) -> tuple[str | None, dict[str, str]]:
    """Best-effort extraction of a title + parameters from the request via LLM."""
    from app.rag.reasoning import get_reasoner

    reasoner = get_reasoner()
    if not reasoner.available:
        return None, {}
    data = reasoner.complete_json(
        "You extract structured fields from a user's request to create an internal "
        "approval note. Only include fields the request clearly implies.",
        f'Request: "{question}"\nApproval Note type: {type_name or "unknown"}\n'
        "Return keys: title (a short UPPERCASE document title) and parameters (an "
        "object with any of: Amount, Vendor, Subject, Justification, Department, "
        "Timeline — only those present in the request).",
        default={},
    )
    if not isinstance(data, dict):
        return None, {}
    title = data.get("title") if isinstance(data.get("title"), str) else None
    raw_params = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
    params = {str(k): str(v) for k, v in raw_params.items() if v and str(v).strip()}
    return (title.strip() if title else None), params


def build_report_suggestion(db: Session, user: User, question: str) -> ApprovalNoteReport:
    types = approval_note_type_service.list_types(db, user, active_only=True)
    letterhead = template_service.get_active_letterhead(db, user)
    options = [ReportTypeOption(id=t.id, name=t.name) for t in types]

    if not letterhead:
        return ApprovalNoteReport(
            status="unavailable",
            prompt=(
                "I can prepare that as an Approval Note, but no company letterhead is "
                "configured yet. Ask an administrator to upload one under Approval "
                "Settings, then try again."
            ),
            available_types=options,
            letterhead_ready=False,
        )
    if not types:
        return ApprovalNoteReport(
            status="unavailable",
            prompt=(
                "No Approval Note types are configured yet. Ask an administrator to add "
                "some under Approval Settings."
            ),
            letterhead_ready=True,
        )

    matched = _match_type(question, types)
    title, params = _extract_details(question, matched.name if matched else None)
    ready = matched is not None

    if ready:
        prompt = (
            f"I can prepare a “{matched.name}”. Review the details below and "
            "generate it — the document opens in the editor for you to refine, then "
            "you can download the DOCX."
        )
    else:
        prompt = (
            "I can prepare that as an Approval Note. Which type is it? Pick one below, "
            "add any details, and I’ll generate the document for you to edit."
        )

    return ApprovalNoteReport(
        status="ready" if ready else "needs_details",
        prompt=prompt,
        available_types=options,
        matched_type_id=matched.id if matched else None,
        matched_type_name=matched.name if matched else None,
        suggested_title=title,
        suggested_parameters=params,
        letterhead_ready=True,
    )
