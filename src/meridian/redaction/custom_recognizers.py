from __future__ import annotations

import re
from dataclasses import dataclass

_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|password|passwd|secret)\s*[:=]\s*\S+"),
]


@dataclass(frozen=True)
class Span:
    entity_type: str
    start: int
    end: int


def find_secret_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            spans.append(Span(entity_type="API_KEY_OR_PASSWORD", start=match.start(), end=match.end()))
    return spans
