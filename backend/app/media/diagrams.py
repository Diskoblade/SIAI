"""Diagram rendering with Mermaid CLI (mmdc → PNG, headless Chromium).

The LLM emits Mermaid source (flowchart, sequence, etc.); we render it to a PNG
for embedding in a slide. Rendering is sandboxed (no network needed) and
best-effort — a failure returns None and the slide simply omits the image.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from app.core.config import settings

# backend/ working dir is where uvicorn runs; resolve mmdc relative to it.
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _mmdc_path() -> Path:
    p = Path(settings.mermaid_cli_path)
    return p if p.is_absolute() else (_BACKEND_DIR / p)


def available() -> bool:
    return settings.diagrams_enabled and _mmdc_path().exists()


def _clean(code: str) -> str:
    """Strip ```mermaid fences and surrounding whitespace."""
    code = code.strip()
    code = re.sub(r"^```(?:mermaid)?\s*", "", code)
    code = re.sub(r"\s*```$", "", code)
    return code.strip()


def render_png(mermaid_code: str) -> bytes | None:
    if not available() or not mermaid_code or not mermaid_code.strip():
        return None
    code = _clean(mermaid_code)
    with tempfile.TemporaryDirectory() as d:
        inp = Path(d) / "diagram.mmd"
        out = Path(d) / "diagram.png"
        cfg = Path(d) / "puppeteer.json"
        inp.write_text(code, encoding="utf-8")
        cfg.write_text('{"args":["--no-sandbox","--disable-setuid-sandbox","--disable-gpu"]}')
        try:
            subprocess.run(
                [
                    str(_mmdc_path()),
                    "-i", str(inp),
                    "-o", str(out),
                    "-p", str(cfg),
                    "-b", "white",
                    "-s", "2",
                ],
                capture_output=True,
                timeout=60,
                check=True,
            )
        except Exception:  # noqa: BLE001 - subprocess/render failure is non-fatal
            return None
        return out.read_bytes() if out.exists() and out.stat().st_size else None
