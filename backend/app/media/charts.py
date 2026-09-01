"""Chart rendering with Vega-Lite (via vl-convert — no browser required).

A slide's chart is described either by a full Vega-Lite `spec`, or by a compact
`{kind, x, y, data}` shape that we expand into a spec. Rendered to PNG bytes.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings

try:  # optional dependency
    import vl_convert as vlc

    _AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    _AVAILABLE = False


_MARKS = {
    "bar": "bar",
    "column": "bar",
    "line": "line",
    "area": "area",
    "point": "point",
    "scatter": "point",
    "pie": "arc",
}


def available() -> bool:
    return _AVAILABLE and settings.charts_enabled


def build_spec(chart: dict[str, Any]) -> dict[str, Any]:
    """Expand a compact chart description into a Vega-Lite spec.

    Accepts `chart["spec"]` (a raw Vega-Lite spec) verbatim, otherwise builds
    one from kind/x/y/data.
    """
    if isinstance(chart.get("spec"), dict):
        return chart["spec"]

    kind = str(chart.get("kind") or "bar").lower()
    mark = _MARKS.get(kind, "bar")
    data = chart.get("data") or []
    x = chart.get("x") or "label"
    y = chart.get("y") or "value"

    spec: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "background": "white",
        "width": 560,
        "height": 340,
        "data": {"values": data},
    }
    if chart.get("title"):
        spec["title"] = str(chart["title"])

    if mark == "arc":
        spec["mark"] = {"type": "arc"}
        spec["encoding"] = {
            "theta": {"field": y, "type": "quantitative"},
            "color": {"field": x, "type": "nominal"},
        }
    else:
        spec["mark"] = {"type": mark, "tooltip": True}
        spec["encoding"] = {
            "x": {"field": x, "type": "nominal", "title": str(x).title()},
            "y": {"field": y, "type": "quantitative", "title": str(y).title()},
        }
        if chart.get("color"):
            spec["encoding"]["color"] = {"field": chart["color"], "type": "nominal"}
    return spec


def render_png(chart: dict[str, Any], *, scale: float = 2.0) -> bytes | None:
    """Render a chart description to PNG bytes, or None if unavailable/invalid."""
    if not available():
        return None
    try:
        spec = build_spec(chart)
        if not (spec.get("data", {}).get("values")):
            return None
        return vlc.vegalite_to_png(vl_spec=json.dumps(spec), scale=scale)
    except Exception:  # noqa: BLE001 - chart rendering is best-effort
        return None
