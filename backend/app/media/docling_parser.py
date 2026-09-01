"""Optional Docling integration for high-quality document parsing.

Docling produces structure-aware Markdown (headings, tables, lists) from PDFs,
DOCX, PPTX, etc. It is a heavy ML dependency, so it is used only when installed
(`pip install docling`); otherwise ingestion falls back to pypdf/python-docx.

Returns Markdown text; the ingestion pipeline turns that into structured chunks.
"""

from __future__ import annotations

import io

from app.core.config import settings

# Extensions Docling handles well; others keep the existing parsers.
# Docling is used for prose/layout documents. Spreadsheets (.xlsx/.csv) are
# handled by the dedicated row-oriented parser instead, which produces clean,
# self-describing "Column: value" chunks that retrieve far better than a wide
# Markdown table.
SUPPORTED = (".pdf", ".docx", ".pptx", ".html", ".md")


def available() -> bool:
    if not settings.docling_enabled:
        return False
    try:
        import docling  # noqa: F401

        return True
    except Exception:  # pragma: no cover - depends on optional heavy dep
        return False


def parse_to_markdown(filename: str, data: bytes) -> str | None:
    """Convert a document to Markdown with Docling, or None if unavailable."""
    if not available() or not filename.lower().endswith(SUPPORTED):
        return None
    try:  # pragma: no cover - exercised only when docling is installed
        from docling.datamodel.base_models import DocumentStream
        from docling.document_converter import DocumentConverter

        stream = DocumentStream(name=filename, stream=io.BytesIO(data))
        result = DocumentConverter().convert(stream)
        markdown = result.document.export_to_markdown()
        return markdown or None
    except Exception:  # noqa: BLE001 - fall back on any Docling error
        return None
