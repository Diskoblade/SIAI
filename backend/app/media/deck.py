"""Turn LLM-proposed visuals into rendered presentation slides.

Charts  -> Vega-Lite spec  -> vl-convert PNG      (app.media.charts)
Diagrams-> Mermaid source  -> mermaid-cli PNG     (app.media.diagrams)
Tables  -> DuckDB analysis -> table               (app.media.analytics)

Every renderer is best-effort: a visual that fails to render is skipped so the
deck is still produced.
"""

from __future__ import annotations

import base64

from app.core.config import settings
from app.media import analytics, charts, diagrams
from app.rag.llm import generate_deck_visuals
from app.schemas.rag import PresentationSlide, PresentationTable


def _b64(png: bytes) -> str:
    return base64.b64encode(png).decode("ascii")


def _title(value, fallback: str) -> str:
    text = " ".join(str(value or "").split()).strip(" .:-")
    return (text or fallback)[:120]


def _chart_slide(visual: dict) -> PresentationSlide | None:
    if not charts.available():
        return None
    chart = dict(visual.get("chart") or {})
    if visual.get("title") and not chart.get("title"):
        chart["title"] = visual["title"]

    # Optional DuckDB aggregation of the chart's raw data before plotting.
    sql = chart.get("sql") or visual.get("sql")
    data = chart.get("data")
    if sql and data and analytics.available():
        agg = analytics.run_analysis(data, sql)
        if agg and agg["rows"]:
            chart["data"] = [dict(zip(agg["columns"], row)) for row in agg["rows"]]
            chart.setdefault("x", agg["columns"][0])
            if len(agg["columns"]) > 1:
                chart.setdefault("y", agg["columns"][1])

    png = charts.render_png(chart)
    if not png:
        return None
    return PresentationSlide(
        layout="chart",
        title=_title(visual.get("title") or chart.get("title"), "Chart"),
        image_base64=_b64(png),
        image_alt=_title(visual.get("title") or chart.get("title"), "Chart"),
    )


def _diagram_slide(visual: dict) -> PresentationSlide | None:
    if not diagrams.available():
        return None
    png = diagrams.render_png(visual.get("mermaid") or visual.get("diagram") or "")
    if not png:
        return None
    return PresentationSlide(
        layout="diagram",
        title=_title(visual.get("title"), "Diagram"),
        image_base64=_b64(png),
        image_alt=_title(visual.get("title"), "Diagram"),
    )


def _table_from_records(records: list, max_rows: int = 10) -> dict | None:
    """Build a table straight from row dicts (no DuckDB needed)."""
    rows_in = [r for r in records if isinstance(r, dict)]
    if not rows_in:
        return None
    columns: list[str] = []
    for record in rows_in:
        for key in record:
            if key not in columns:
                columns.append(str(key))
    columns = columns[:6]
    rows = [[record.get(c, "") for c in columns] for record in rows_in[:max_rows]]
    return {"columns": columns, "rows": rows}


def _table_slide(visual: dict) -> PresentationSlide | None:
    table = visual.get("table")
    data = visual.get("data")
    if (not table or not table.get("columns")) and data:
        # Try the LLM's DuckDB aggregation; on failure fall back to the raw rows
        # so a table always renders when data is present.
        if analytics.available():
            table = analytics.run_analysis(data, visual.get("sql")) or analytics.run_analysis(data)
        if not table or not table.get("columns"):
            table = _table_from_records(data)
    if not table or not table.get("columns"):
        return None
    columns = [str(c) for c in table["columns"]][:6]
    rows = [[str(c) for c in row][:6] for row in (table.get("rows") or [])][:10]
    if not rows:
        return None
    return PresentationSlide(
        layout="table",
        title=_title(visual.get("title"), "Data"),
        table=PresentationTable(columns=columns, rows=rows),
    )


_BUILDERS = {"chart": _chart_slide, "diagram": _diagram_slide, "table": _table_slide}


def render_visual_slides(visuals: list[dict], *, limit: int | None = None) -> list[PresentationSlide]:
    """Render a list of visual descriptors into slides (skips failures)."""
    limit = limit or settings.deck_max_visuals
    slides: list[PresentationSlide] = []
    for visual in visuals[:limit]:
        if not isinstance(visual, dict):
            continue
        builder = _BUILDERS.get(str(visual.get("kind") or "").lower())
        if builder is None:
            continue
        try:
            slide = builder(visual)
        except Exception:  # noqa: BLE001 - one bad visual must not sink the deck
            slide = None
        if slide is not None:
            slides.append(slide)
    return slides


def _kind_available(kind: str) -> bool:
    # Tables render as a slide grid on the frontend even without DuckDB (DuckDB
    # only adds the optional aggregation), so a table is always producible.
    return {
        "chart": charts.available(),
        "diagram": diagrams.available(),
        "table": True,
    }.get(kind, False)


def _generate_single(topic: str, kind: str, evidence_text: str) -> PresentationSlide | None:
    """Best-effort: get exactly one visual of `kind` from the LLM and render it.

    Retries a couple of times because the LLM occasionally returns a visual that
    fails to render; an explicitly requested type should still appear.
    """
    for _ in range(2):
        for visual in generate_deck_visuals(topic, evidence_text, 3, requested={kind}):
            if str(visual.get("kind") or "").lower() == kind:
                rendered = render_visual_slides([visual], limit=1)
                if rendered:
                    return rendered[0]
    return None


def build_deck_visual_slides(
    topic: str, evidence_text: str = "", requested: set[str] | None = None
) -> list[PresentationSlide]:
    """Render deck visuals. Any explicitly `requested` type (chart/diagram/table)
    is guaranteed to appear when its renderer is available; the rest are
    LLM-proposed."""
    requested = {k for k in (requested or set()) if _kind_available(k)}
    if not requested and not (charts.available() or diagrams.available() or analytics.available()):
        return []

    cap = max(settings.deck_max_visuals, len(requested))
    visuals = generate_deck_visuals(topic, evidence_text, cap, requested=requested)
    slides = render_visual_slides(visuals, limit=cap)

    # Guarantee: fill in any explicitly requested type the LLM/render missed.
    present = {s.layout for s in slides}
    for kind in requested - present:
        slide = _generate_single(topic, kind, evidence_text)
        if slide is not None:
            slides.append(slide)
            present.add(kind)

    # At most one visual per kind for a clean, predictable deck.
    seen: set[str] = set()
    deduped: list[PresentationSlide] = []
    for slide in slides:
        if slide.layout in seen:
            continue
        seen.add(slide.layout)
        deduped.append(slide)

    # Keep explicitly requested visuals first, then cap.
    deduped.sort(key=lambda s: 0 if s.layout in requested else 1)
    return deduped[:cap]
