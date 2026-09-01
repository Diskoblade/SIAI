"""Deterministic classifier for useful, user-authored conversation memories."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.document import MemoryCategory
from app.schemas.memory import MAX_MEMORY_CONTENT_LENGTH


@dataclass(frozen=True)
class ClassifiedMemory:
    category: MemoryCategory
    content: str


_TRANSIENT = re.compile(
    r"^(?:hi|hello|hey|thanks|thank you|ok|okay|yes|no|great|done|continue)[.! ]*$",
    re.IGNORECASE,
)
_RECALL_QUESTION = re.compile(
    r"^(?:do you remember|what did (?:we|i)|which .* did (?:we|i)|remind me)",
    re.IGNORECASE,
)
_DECISION = re.compile(
    r"\b(?:we|i)\s+(?:decided|chose|selected|agreed|settled)\b|\bdecision\s*:",
    re.IGNORECASE,
)
_NOTE = re.compile(
    r"\b(?:remember that|save this|note that|my note|keep in mind)\b",
    re.IGNORECASE,
)
_PREFERENCE = re.compile(
    r"\b(?:i prefer|my preference|i would rather|i like to use)\b",
    re.IGNORECASE,
)


def classify_message(message: str) -> ClassifiedMemory | None:
    content = " ".join(message.split()).strip()
    if len(content) < 12 or len(content) > MAX_MEMORY_CONTENT_LENGTH:
        return None
    if _TRANSIENT.fullmatch(content) or _RECALL_QUESTION.search(content):
        return None
    if _DECISION.search(content):
        category = MemoryCategory.PROJECT_DECISION
    elif _PREFERENCE.search(content):
        category = MemoryCategory.PREFERENCE
    elif _NOTE.search(content):
        category = MemoryCategory.USER_NOTE
    else:
        return None
    return ClassifiedMemory(category=category, content=content)
