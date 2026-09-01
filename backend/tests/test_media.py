"""Tests for deck media: DuckDB analytics, Vega-Lite charts, Mermaid diagrams,
and their assembly into presentation slides."""

from __future__ import annotations

import pytest

from app.media import analytics, charts, deck, diagrams
from app.rag.presentation import detect_requested_visuals

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_detect_requested_visuals():
    assert detect_requested_visuals("Create a 5-slide deck about X with a bar chart") == {"chart"}
    assert detect_requested_visuals("presentation about Y with a flowchart") == {"diagram"}
    assert "table" in detect_requested_visuals("slides with a comparison table")
    assert detect_requested_visuals(
        "deck on sales with a chart and a data table"
    ) == {"chart", "table"}
    assert detect_requested_visuals("Create a presentation about photosynthesis") == set()
    # Subject-matter uses must NOT trigger (no request connector).
    assert detect_requested_visuals("Create a presentation about the periodic table") == set()
    assert detect_requested_visuals("Create a deck about org chart best practices") == set()


def test_requested_table_is_guaranteed(monkeypatch):
    """When a table is explicitly requested, one is added even if the bulk LLM
    call returns no visuals."""

    def fake_gen(topic, evidence, maxv, requested=None):
        if requested == {"table"}:  # the guarantee retry
            return [{"kind": "table", "title": "T", "table": {"columns": ["A", "B"], "rows": [["1", "2"]]}}]
        return []  # bulk call proposes nothing

    monkeypatch.setattr(deck, "generate_deck_visuals", fake_gen)
    slides = deck.build_deck_visual_slides("some topic", requested={"table"})
    assert any(s.layout == "table" for s in slides)


# --------------------------------------------------------------------------- #
# DuckDB analytics
# --------------------------------------------------------------------------- #
def test_duckdb_aggregation():
    if not analytics.available():
        pytest.skip("duckdb not installed")
    records = [
        {"dept": "Finance", "amount": 500},
        {"dept": "Finance", "amount": 300},
        {"dept": "HR", "amount": 120},
    ]
    out = analytics.run_analysis(
        records, "SELECT dept, SUM(amount) AS total FROM data GROUP BY dept ORDER BY total DESC"
    )
    assert out["columns"] == ["dept", "total"]
    assert out["rows"][0] == ["Finance", 800]


def test_duckdb_rejects_non_select():
    if not analytics.available():
        pytest.skip("duckdb not installed")
    records = [{"a": 1}]
    # A destructive statement must be ignored (falls back to plain select).
    out = analytics.run_analysis(records, "DROP TABLE data")
    assert out is not None and out["columns"] == ["a"]


# --------------------------------------------------------------------------- #
# Vega-Lite charts
# --------------------------------------------------------------------------- #
def test_chart_renders_png():
    if not charts.available():
        pytest.skip("vl-convert not installed")
    chart = {
        "type": "bar",
        "x": "dept",
        "y": "count",
        "data": [{"dept": "Finance", "count": 12}, {"dept": "HR", "count": 7}],
    }
    png = charts.render_png(chart)
    assert png and png.startswith(_PNG_MAGIC)


def test_chart_empty_data_returns_none():
    if not charts.available():
        pytest.skip("vl-convert not installed")
    assert charts.render_png({"type": "bar", "x": "a", "y": "b", "data": []}) is None


# --------------------------------------------------------------------------- #
# Mermaid diagrams (skipped when mmdc is not installed)
# --------------------------------------------------------------------------- #
def test_diagram_renders_png():
    if not diagrams.available():
        pytest.skip("mermaid-cli (mmdc) not installed")
    png = diagrams.render_png("flowchart LR\n A[Start] --> B[End]")
    assert png and png.startswith(_PNG_MAGIC)


# --------------------------------------------------------------------------- #
# Deck assembly
# --------------------------------------------------------------------------- #
def test_render_visual_slides_mixed():
    visuals = [
        {
            "kind": "chart",
            "title": "Docs",
            "chart": {"type": "bar", "x": "d", "y": "n", "data": [{"d": "A", "n": 3}]},
        },
        {
            "kind": "table",
            "title": "Totals",
            "data": [{"dept": "Finance", "amount": 500}, {"dept": "HR", "amount": 120}],
            "sql": "SELECT dept, SUM(amount) AS total FROM data GROUP BY dept",
        },
    ]
    slides = deck.render_visual_slides(visuals)
    layouts = {s.layout for s in slides}
    # chart requires vl-convert; table requires duckdb — assert whatever is available.
    if charts.available():
        assert "chart" in layouts
        assert any(s.image_base64 for s in slides if s.layout == "chart")
    if analytics.available():
        assert "table" in layouts
        table_slide = next(s for s in slides if s.layout == "table")
        assert table_slide.table.columns and table_slide.table.rows
