"""Deterministic presentation routing and authorized slide-outline creation."""

from __future__ import annotations

import re
import unicodedata

from app.core.config import settings
from app.rag.pipeline import RagResult
from app.schemas.rag import PresentationSlide, PresentationSpec

_SLIDE_NOUN = re.compile(
    r"\b(?:pptx?|power\s*point|slide\s*deck|presentation|slides?)\b", re.IGNORECASE
)
_CREATE_ACTION = re.compile(
    r"\b(?:create|make|generate|prepare|build|draft|produce|turn|convert|summari[sz]e)\b",
    re.IGNORECASE,
)
_SLIDE_PHRASE = re.compile(
    r"\b(?:slides?|pptx?|presentation)\s+(?:about|on|for|from|covering)\b",
    re.IGNORECASE,
)
_CITATION = re.compile(r"\[(C\d+)\]")


def is_slide_request(question: str) -> bool:
    """Require both a slide noun and creation intent to avoid false triggers."""
    return bool(
        _SLIDE_NOUN.search(question)
        and (_CREATE_ACTION.search(question) or _SLIDE_PHRASE.search(question))
    )


def presentation_topic(question: str) -> str:
    """The underlying subject to *retrieve* on for a slide request.

    Strips the deck-command words ("create a 5-slide presentation about …") so
    retrieval matches departmental documents on the real topic instead of the
    boilerplate. Returns "" when no meaningful topic remains.
    """
    topic = _presentation_title(question)
    return "" if topic == "Departmental Knowledge Briefing" else topic


# A request connector must precede the visual word, so subject-matter uses
# ("periodic table", "org chart", "database architecture") do NOT trigger.
_REQUEST = (
    r"\b(?:with|include|including|add|adding|show|showing|display|feature|featuring|"
    r"containing|using|plus|and|also|as|a)\s+(?:a|an|some|the|one|two|three)?\s*"
)
_VISUAL_PATTERNS = {
    "chart": re.compile(
        _REQUEST + r"(?:bar\s+|pie\s+|line\s+|column\s+)?(?:charts?|graphs?|plots?|histograms?)\b",
        re.IGNORECASE,
    ),
    "diagram": re.compile(
        _REQUEST + r"(?:flow\s?charts?|flowcharts?|diagrams?|workflows?|"
        r"sequence\s+diagrams?|architecture\s+diagrams?|mermaid)\b",
        re.IGNORECASE,
    ),
    "table": re.compile(
        _REQUEST + r"(?:data\s+|comparison\s+)?(?:tables?|matrix|spreadsheets?)\b",
        re.IGNORECASE,
    ),
}


def detect_requested_visuals(question: str) -> set[str]:
    """Return the visual types (chart / diagram / table) explicitly requested.

    A request connector ("with a chart", "including a table") is required, so a
    subject that merely contains a visual word ("periodic table", "org chart")
    does not trigger. When a type is detected the deck builder guarantees at
    least one visual of that type (if its renderer is available).
    """
    return {kind for kind, pattern in _VISUAL_PATTERNS.items() if pattern.search(question)}


def _requested_slide_count(question: str) -> int:
    patterns = (
        r"\b(\d{1,2})\s*[- ]?slides?\b",
        r"\bslides?\s*[:=-]?\s*(\d{1,2})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            return max(3, min(int(match.group(1)), 10))
    return 6


def _presentation_title(question: str) -> str:
    title = question.strip()
    title = re.sub(
        r"^\s*(?:please\s+)?(?:create|make|generate|prepare|build|draft|produce|turn|convert)\s+",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"\b(?:a|an)?\s*\d{1,2}\s*[- ]?slides?\b", "", title, flags=re.IGNORECASE)
    title = re.sub(
        r"\b(?:a|an)?\s*(?:pptx?|power\s*point|slide\s*deck|presentation|slides?)\b",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"^\s*(?:about|on|for|from|covering)\s+", "", title, flags=re.IGNORECASE)
    # Strip explicit visual-request phrases ("with a chart and a table") so the
    # topic/title is the real subject, not the visual instructions.
    _visual_words = (
        r"(?:bar\s+|pie\s+|line\s+)?(?:charts?|graphs?|plots?|diagrams?|flow\s?charts?|"
        r"tables?|data\s+tables?|visuali[sz]ations?|infographics?|matrix)"
    )
    # A connector is REQUIRED so real subjects ("periodic table", "org chart")
    # are not mistaken for visual instructions.
    title = re.sub(
        r"\s*[,]?\s*\b(?:with|including|featuring|containing|plus|and)\b\s+(?:a|an|some|the)?\s*"
        + _visual_words,
        " ",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"\s+(?:and|with|plus|,)\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" .,:;-_")
    if not title:
        return "Departmental Knowledge Briefing"
    if title.islower():
        title = title.title()
    return _truncate(title, 100)


def _truncate(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."


def _strip_markdown(text: str) -> str:
    """Remove Markdown formatting so slide text reads as clean prose.

    Handles headings (``###``), bold/italic (``**x**``, ``*x*``, ``__x__``,
    ``_x_``), inline code, blockquotes, links, and list/number markers.
    Underscore emphasis is only stripped when word-bounded, so identifiers such
    as ``dept_finance`` survive intact.
    """
    if not text:
        return text
    s = text
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)  # [label](url) -> label
    s = re.sub(r"^\s*#{1,6}\s*", "", s)  # heading marker
    s = re.sub(r"^\s*>\s*", "", s)  # blockquote
    s = re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s+", "", s)  # list / numbered marker
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)  # **bold**
    s = re.sub(r"__(.+?)__", r"\1", s)  # __bold__
    s = re.sub(r"\*(?!\s)(.+?)(?<!\s)\*", r"\1", s)  # *italic*
    s = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", s)  # _italic_ (word-bounded)
    s = re.sub(r"`([^`]+)`", r"\1", s)  # `code`
    s = re.sub(r"[*`#]+", "", s)  # stray markers (underscores left untouched)
    return " ".join(s.split()).strip(" .,:;-")


def _answer_bullets(answer: str, *, limit: int = 5) -> list[str]:
    lines = []
    for line in answer.splitlines():
        clean = _strip_markdown(line)
        if (
            not clean
            or clean.lower().startswith("based on the authorized")
            or clean.lower().startswith("no relevant authorized document was found")
        ):
            continue
        lines.append(_truncate(clean, 220))
    if len(lines) <= 1:
        sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
        lines = [
            _truncate(cleaned, 220)
            for sentence in sentences
            if (cleaned := _strip_markdown(sentence))
            and not cleaned.lower().startswith("based on the authorized")
            and not cleaned.lower().startswith("no relevant authorized document was found")
        ]
    return lines[:limit]


def _bullet_title(bullet: str, index: int) -> str:
    clean = _strip_markdown(re.sub(r"\[(?:C\d+)\]", "", bullet))
    heading = re.split(r"\s*[:;-]\s+", clean, maxsplit=1)[0]
    words = heading.split()
    if len(words) > 8 or len(heading) > 70:
        heading = " ".join(clean.split()[:7])
    heading = heading.strip(" .,:;-")
    return _truncate(heading or f"Key point {index}", 70)


def _evidence_source_line(item: dict) -> str:
    location = []
    if item.get("page") is not None:
        location.append(f"page {item['page']}")
    if item.get("section"):
        location.append(_strip_markdown(str(item["section"])))
    suffix = f" ({', '.join(location)})" if location else ""
    title = _strip_markdown(str(item.get("document_title") or "Source"))
    return _truncate(f"[{item['citation_id']}] {title}{suffix}", 200)


def _safe_filename(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_title).strip("-").lower()
    return f"{(slug or 'department-briefing')[:80]}.pptx"


def content_slide_budget(question: str) -> int:
    """How many general-knowledge content slides to request from the LLM.

    Reserves one slide for the title and one for the source/notice slide.
    """
    return max(1, _requested_slide_count(question) - 2)


def build_presentation_spec(
    question: str,
    result: RagResult,
    *,
    gk_outline: list[dict] | None = None,
    media_slides: list | None = None,
) -> PresentationSpec | None:
    if not is_slide_request(question):
        return None

    title = _presentation_title(question)
    desired_count = _requested_slide_count(question)
    valid_ids = {citation.citation_id for citation in result.citations}

    # Evidence the answer itself cited (fully grounded documents answer).
    validated = [item for item in result.evidence if item.get("citation_id") in valid_ids]
    # On-topic authorized evidence the answer step graded "incomplete" and
    # dropped. A deck should still cite it (verbatim, with the source) rather
    # than silently fall back to general knowledge — it is authorization-safe.
    threshold = settings.evidence_sufficiency_threshold
    relevant = [
        item
        for item in result.evidence
        if item.get("citation_id") not in valid_ids and item.get("score", 0.0) >= threshold
    ]
    deck_evidence = validated or relevant
    partial_coverage = bool(deck_evidence) and not validated

    slides: list[PresentationSlide] = []
    source_mode = "documents" if deck_evidence else result.answer_source

    if deck_evidence:
        summary = _answer_bullets(result.answer) if validated else []
        slides.append(
            PresentationSlide(
                layout="summary",
                title="Key findings",
                bullets=summary
                or ["Key points drawn from your authorized departmental sources."],
                source_ids=[str(item["citation_id"]) for item in deck_evidence],
            )
        )

        # Reserve the final slide for traceable source references.
        evidence_slots = max(1, desired_count - 3)
        for index, item in enumerate(deck_evidence[:evidence_slots], start=1):
            citation_id = str(item["citation_id"])
            heading = _strip_markdown(
                item.get("section") or item.get("document_title") or f"Evidence {index}"
            )
            snippet = _truncate(_strip_markdown(str(item.get("text", ""))), 480)
            slides.append(
                PresentationSlide(
                    layout="evidence",
                    title=_truncate(str(heading), 100),
                    bullets=[f"{snippet} [{citation_id}]"],
                    source_ids=[citation_id],
                )
            )

        slides.append(
            PresentationSlide(
                layout="sources",
                title="Sources",
                bullets=[_evidence_source_line(item) for item in deck_evidence],
                source_ids=[str(item["citation_id"]) for item in deck_evidence],
            )
        )

        if partial_coverage:
            slides.append(
                PresentationSlide(
                    layout="notice",
                    title="Coverage note",
                    bullets=[
                        "These slides cite your authorized departmental source(s) on this topic.",
                        "The available document may not fully cover the request — verify completeness.",
                    ],
                )
            )

    elif source_mode == "general_knowledge":
        content_slots = max(1, desired_count - 2)
        built = False

        # Preferred: a structured outline from the LLM (complete bullets, clean
        # titles — no content dropped by prose parsing).
        if gk_outline:
            for item in gk_outline[:content_slots]:
                slide_title = _truncate(_strip_markdown(str(item.get("title") or "")), 80)
                bullets = [
                    _truncate(_strip_markdown(str(b)), 220)
                    for b in (item.get("bullets") or [])
                    if str(b).strip()
                ]
                if not slide_title and not bullets:
                    continue
                slides.append(
                    PresentationSlide(
                        layout="summary",
                        title=slide_title or "Overview",
                        bullets=bullets[:5] or [slide_title],
                    )
                )
            built = bool(slides)

        # Fallback: parse the prose general-knowledge answer into bullets.
        if not built:
            points = _answer_bullets(result.answer, limit=max(8, content_slots))
            # Skip long intro/closing prose (no "heading: detail" structure) so
            # slides carry real points, not a truncated opening sentence.
            structured = [p for p in points if ":" in p[:60]] or points
            for index, point in enumerate(structured[:content_slots], start=1):
                heading, _, detail = point.partition(":")
                slides.append(
                    PresentationSlide(
                        layout="summary",
                        title=_bullet_title(point, index),
                        bullets=[detail.strip() or point] if detail.strip() else [point],
                    )
                )
            built = bool(slides)

        if built:
            slides.append(
                PresentationSlide(
                    layout="notice",
                    title="About this content",
                    bullets=[
                        "No relevant authorized departmental document matched the request.",
                        "These slides use general model knowledge and may be incomplete or outdated.",
                        "Verify important facts before relying on this presentation.",
                    ],
                )
            )
        else:
            source_mode = "unavailable"

    if not slides:
        slides.append(
            PresentationSlide(
                layout="notice",
                title="Answer unavailable",
                bullets=[
                    "No authorized departmental sources matched this request.",
                    "Configure an LLM provider for general-knowledge fallback, or upload relevant documents.",
                ],
            )
        )

    # Insert rendered visuals (charts / diagrams / data tables) just before the
    # trailing Sources / notice slides.
    if media_slides:
        split = next(
            (i for i, s in enumerate(slides) if s.layout in ("sources", "notice")),
            len(slides),
        )
        slides = slides[:split] + list(media_slides) + slides[split:]

    subtitle = {
        "documents": (
            "Generated from authorized departmental evidence"
            + (" (partial coverage)" if partial_coverage else "")
        ),
        "general_knowledge": "Generated from general model knowledge",
    }.get(source_mode, "No authorized sources available")

    return PresentationSpec(
        filename=_safe_filename(title),
        title=title,
        subtitle=subtitle,
        slide_count=len(slides) + 1,
        slides=slides,
        source_mode=source_mode,
    )
