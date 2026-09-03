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


_STREET_SUFFIXES = (
    r"Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Lane|Ln|Drive|Dr|"
    r"Court|Ct|Way|Place|Pl|Terrace|Ter|Circle|Cir|Trail|Trl|Parkway|Pkwy|"
    r"Highway|Hwy|Square|Sq"
)

# best-effort heuristic for common US-style street addresses - not exhaustive,
# presidio has no built-in street-address recognizer to fall back on.
_ADDRESS_PATTERN = re.compile(
    rf"\b\d{{1,6}}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){{0,3}}\s+"
    rf"(?:{_STREET_SUFFIXES})\b\.?"
    rf"(?:,?\s+(?:Apt|Suite|Ste|Unit|#)\.?\s*\w+)?"
    rf"(?:,?\s+[A-Za-z ]+,?\s+[A-Z]{{2}}\s+\d{{5}}(?:-\d{{4}})?)?",
    re.IGNORECASE,
)


def find_address_spans(text: str) -> list[Span]:
    return [
        Span(entity_type="HOME_ADDRESS", start=match.start(), end=match.end())
        for match in _ADDRESS_PATTERN.finditer(text)
    ]
