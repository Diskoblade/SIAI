"""Answer generation, abstracted over the LLM provider (spec #18, #19).

Nodes never depend on Ollama-specific APIs. Two providers:
  * ExtractiveAnswerer — default; deterministic, no external call. Builds an
    answer strictly from the provided evidence with citation markers. Perfect
    for running/testing the whole pipeline offline.
  * OpenAICompatLLM — any OpenAI-compatible /chat/completions endpoint
    (Ollama at /v1, or vLLM). Grounded answers are restricted to supplied
    evidence. When retrieval is exhausted, it can produce a clearly labelled
    answer from general model knowledge without document citations.

The grounded answer model is only ever given already-authorized evidence. The
general-knowledge fallback receives the question alone.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from app.core.config import settings

SYSTEM_PROMPT = (
    "You are a departmental knowledge assistant. Ground factual claims about "
    "documents ONLY in the provided evidence, and reference it like [C1]. You may "
    "ALSO use the conversation history in the message to resolve references and "
    "recall details the user shared earlier (names, numbers, decisions, "
    "preferences) — answer those from the conversation without a citation. Do not "
    "invent unsupported facts. If neither the evidence nor the conversation "
    "contains the answer, say so."
)

INSUFFICIENT = "The available departmental evidence is insufficient to answer this question."
GENERAL_KNOWLEDGE_NOTICE = (
    "No relevant authorized document was found. The following answer is based on "
    "general model knowledge and may be incomplete or outdated."
)
GENERAL_KNOWLEDGE_UNAVAILABLE = (
    "No relevant authorized document was found, and a general-knowledge answer "
    "requires a configured LLM provider."
)

# Cues that the current message is recalling something from the conversation
# rather than asking a general-knowledge question.
_RECALL_CUES = re.compile(
    r"\b(?:my|i\s+(?:mentioned|said|told|shared|gave)|you\s+said|earlier|"
    r"previously|remember|recall|what\s+did\s+i|what'?s?\s+my|the\s+\w+\s+i\s+"
    r"(?:mentioned|gave|told|shared))\b",
    re.IGNORECASE,
)


def _looks_like_conversation_recall(question: str) -> bool:
    """True when the message carries conversation history and the current turn
    is asking about a detail the user shared earlier."""
    if "Conversation history:" not in question:
        return False
    current = question.split("Current question:")[-1]
    return bool(_RECALL_CUES.search(current))

AnswerSource = Literal["documents", "general_knowledge", "calculation", "unavailable"]


def _format_evidence(evidence: list[dict]) -> str:
    lines = []
    for e in evidence:
        loc = []
        if e.get("page") is not None:
            loc.append(f"p.{e['page']}")
        if e.get("section"):
            loc.append(e["section"])
        loc_str = f" ({', '.join(loc)})" if loc else ""
        lines.append(f"[{e['citation_id']}] {e['document_title']}{loc_str}: {e['text']}")
    return "\n\n".join(lines)


class ExtractiveAnswerer:
    """Deterministic answer built from the top evidence, with citations."""

    supports_general_knowledge = False

    def generate(self, question: str, evidence: list[dict]) -> str:
        if not evidence:
            return INSUFFICIENT
        parts = ["Based on the authorized departmental documents:"]
        for e in evidence[:3]:
            snippet = " ".join(e["text"].split())
            if len(snippet) > 300:
                snippet = snippet[:300].rsplit(" ", 1)[0] + "…"
            parts.append(f"- {snippet} [{e['citation_id']}]")
        return "\n".join(parts)

    def generate_general_knowledge(self, question: str) -> str:
        return GENERAL_KNOWLEDGE_UNAVAILABLE

    def generate_slide_outline(self, topic: str, count: int) -> list[dict]:
        return []

    def generate_deck_visuals(
        self, topic: str, evidence_text: str, max_visuals: int, requested=None
    ) -> list[dict]:
        return []


class OpenAICompatLLM:
    """Calls an OpenAI-compatible chat endpoint (Ollama /v1, vLLM, …)."""

    supports_general_knowledge = True

    def _complete(self, system_prompt: str, user_content: str, *, temperature: float) -> str:
        import time

        import httpx  # local import so the default path needs no httpx

        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"

        # A deck request fires many sequential calls; retry on rate limits (429)
        # and transient 5xx with backoff so later calls (e.g. visuals) are not
        # silently dropped.
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                with httpx.Client(timeout=120) as client:
                    resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 429 or resp.status_code >= 500:
                    retry_after = resp.headers.get("retry-after")
                    delay = float(retry_after) if retry_after else 1.5 * (attempt + 1)
                    time.sleep(min(delay, 10.0))
                    last_error = httpx.HTTPStatusError(
                        "retryable", request=resp.request, response=resp
                    )
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(1.2 * (attempt + 1))
        raise last_error or RuntimeError("LLM request failed")

    def generate(self, question: str, evidence: list[dict]) -> str:
        if not evidence:
            return INSUFFICIENT

        user_content = (
            f"Question: {question}\n\nEvidence:\n{_format_evidence(evidence)}\n\n"
            "Answer using only the evidence above and cite IDs like [C1]."
        )
        return self._complete(SYSTEM_PROMPT, user_content, temperature=0.0)

    def generate_general_knowledge(self, question: str) -> str:
        system_prompt = (
            "You are a helpful assistant. The message may include earlier "
            "conversation history. FIRST, if the user is asking about something they "
            "shared earlier in the conversation (a name, number, preference, or "
            "decision), answer from that conversation context and state the specific "
            "detail. Otherwise, answer from broad general knowledge. Do not fabricate "
            "confidential organizational policies or records that were not stated. Do "
            "not include citation markers such as [C1]. For a slide request, return 5 "
            "to 8 concise, presentation-ready points with short headings."
        )
        answer = self._complete(
            system_prompt,
            f"{question}\n\nAnswer using the conversation context above when relevant, "
            "otherwise from general knowledge.",
            temperature=0.2,
        )
        answer = re.sub(r"\[(?:C\d+)\]", "", answer).strip()
        # If the answer came from the conversation, the "no document" notice is
        # misleading; only prepend it for genuinely general-knowledge answers.
        if _looks_like_conversation_recall(question):
            return answer
        return f"{GENERAL_KNOWLEDGE_NOTICE}\n\n{answer}"

    def generate_slide_outline(self, topic: str, count: int) -> list[dict]:
        """Return a structured deck outline: [{"title", "bullets": [...]}, ...].

        Produces exactly `count` presentation-ready content slides from general
        model knowledge — complete bullets, clean titles, no dropped content.
        """
        count = max(1, min(count, 12))
        system_prompt = (
            "You design presentation deck outlines. Return ONLY valid JSON of the "
            'form {"slides": [{"title": "...", "bullets": ["...", "..."]}]}. '
            f"Produce exactly {count} content slides for the given topic. Each slide "
            "has a concise title (at most 8 words) and 2 to 4 short factual bullet "
            "points (each at most 22 words). Cover the topic completely and in a "
            "logical order across the slides. Use only broad general knowledge; do "
            "not invent confidential organizational policies, decisions, names, or "
            "records. Plain text only — no markdown symbols such as # or *."
        )
        raw = self._complete(system_prompt, f"Topic: {topic}", temperature=0.2)
        return _parse_slide_outline(raw)

    def generate_deck_visuals(
        self, topic: str, evidence_text: str, max_visuals: int, requested=None
    ) -> list[dict]:
        """Ask the LLM to propose data visuals (charts / diagrams / tables)."""
        max_visuals = max(1, min(max_visuals, 6))
        must = sorted(requested or [])
        must_line = (
            f" The user explicitly asked for these visual types: {', '.join(must)}. "
            "You MUST include at least one visual of EACH of those types."
            if must
            else ""
        )
        system_prompt = (
            "You add data visuals to a slide deck. Return ONLY valid JSON: "
            '{"visuals": [ ... ]}. Propose at most '
            f"{max_visuals} visuals that genuinely aid understanding of the topic.{must_line} "
            "Each visual is one of:\n"
            '  {"kind":"chart","title":"...","chart":{"type":"bar|line|pie",'
            '"x":"<field>","y":"<field>","data":[{"<field>":..,"<field>":..}, ...]}}'
            " — include 3 to 8 illustrative data rows.\n"
            '  {"kind":"diagram","title":"...","mermaid":"<valid mermaid code, e.g. flowchart LR; A-->B>"}\n'
            '  {"kind":"table","title":"...","data":[{...}, ...],"sql":"SELECT ... FROM data ..."}'
            " — sql is an optional DuckDB aggregation over the provided data (table name is data).\n"
            "Use only broad general knowledge or the evidence provided; do not invent "
            "confidential organizational records, names, or figures. If no visual clearly "
            "helps, return an empty list. Plain text labels only — no markdown symbols."
        )
        user = f"Topic: {topic}\n\nEvidence (may be empty):\n{(evidence_text or '')[:2000]}"
        raw = self._complete(system_prompt, user, temperature=0.2)
        data = _parse_json_object(raw)
        visuals = data.get("visuals") if isinstance(data, dict) else None
        return [v for v in visuals if isinstance(v, dict)] if isinstance(visuals, list) else []


def _parse_json_object(raw: str) -> dict:
    """Best-effort parse of a JSON object from an LLM response."""
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def _parse_slide_outline(raw: str) -> list[dict]:
    """Best-effort parse of a slides JSON payload into a list of dicts."""
    data = _parse_json_object(raw)
    slides = data.get("slides")
    if not isinstance(slides, list):
        return []
    outline: list[dict] = []
    for item in slides:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        bullets = [str(b).strip() for b in (item.get("bullets") or []) if str(b).strip()]
        if title or bullets:
            outline.append({"title": title, "bullets": bullets})
    return outline


def generate_general_knowledge_slides(topic: str, count: int) -> list[dict]:
    """Generate a structured general-knowledge deck outline (empty if no LLM)."""
    answerer = get_answerer()
    generate = getattr(answerer, "generate_slide_outline", None)
    if generate is None:
        return []
    try:
        return generate(topic, count)
    except Exception:  # noqa: BLE001 - deck generation is best-effort
        return []


def generate_deck_visuals(
    topic: str, evidence_text: str, max_visuals: int, requested=None
) -> list[dict]:
    """Ask the configured LLM for deck visuals (charts/diagrams/tables)."""
    answerer = get_answerer()
    generate = getattr(answerer, "generate_deck_visuals", None)
    if generate is None:
        return []
    try:
        return generate(topic, evidence_text, max_visuals, requested=requested)
    except Exception:  # noqa: BLE001 - best-effort
        return []


def generate_answer(question: str, evidence: list[dict]) -> tuple[str, AnswerSource]:
    """Select a grounded answer first, then the explicitly ungrounded fallback."""
    answerer = get_answerer()
    if evidence:
        return answerer.generate(question, evidence), "documents"
    if (
        settings.rag_general_knowledge_fallback_enabled
        and answerer.supports_general_knowledge
    ):
        return answerer.generate_general_knowledge(question), "general_knowledge"
    return GENERAL_KNOWLEDGE_UNAVAILABLE, "unavailable"


_answerer = None


def get_answerer():
    global _answerer
    if _answerer is None:
        _answerer = OpenAICompatLLM() if settings.llm_provider == "openai" else ExtractiveAnswerer()
    return _answerer


def reset_answerer() -> None:
    global _answerer
    _answerer = None
