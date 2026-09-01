"""Reasoning LLM for the agentic nodes (query understanding, planning, grading,
rewriting, claim verification).

Provider-agnostic. When `LLM_PROVIDER=openai` a real OpenAI-compatible chat
model (OpenAI/ChatGPT, Azure, Ollama /v1, vLLM) is used; otherwise a
`NullReasoner` reports `available=False` and every node falls back to
deterministic heuristics, so the graph runs fully offline.

Reasoning is used only for *reasoning* — never for security decisions
(scope resolution, filtering, citation validation stay deterministic).
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import settings


class NullReasoner:
    available = False

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - trivial
        raise RuntimeError("No reasoning LLM configured.")

    def complete_json(self, system: str, user: str, default: Any) -> Any:
        return default


class OpenAIReasoner:
    available = True

    def __init__(self) -> None:
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    def complete(self, system: str, user: str) -> str:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    def complete_json(self, system: str, user: str, default: Any) -> Any:
        try:
            raw = self.complete(system + "\nRespond with ONLY valid JSON.", user)
            return _extract_json(raw)
        except Exception:  # noqa: BLE001 - reasoning is best-effort; fall back
            return default


def _extract_json(text: str) -> Any:
    text = text.strip()
    # Strip ```json fences if present.
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"[\{\[].*[\}\]]", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


_reasoner: NullReasoner | OpenAIReasoner | None = None


def get_reasoner():
    global _reasoner
    if _reasoner is None:
        _reasoner = OpenAIReasoner() if settings.llm_provider == "openai" else NullReasoner()
    return _reasoner


def reset_reasoner() -> None:
    global _reasoner
    _reasoner = None
