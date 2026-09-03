from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenizationResult:
    tokenized_text: str
    mapping: dict[str, str]
    entity_counts: dict[str, int]


def _spans_overlap(a: Any, b: Any) -> bool:
    return a.start < b.end and b.start < a.end


def _merge_spans(presidio_spans: list[Any], custom_spans: list[Any]) -> list[Any]:
    """merges presidio's own results with our custom regex spans, dropping
    any custom span that overlaps a presidio span already found - presidio's
    own detections take priority so the same text is never double-processed."""
    merged = list(presidio_spans)
    for custom_span in custom_spans:
        if not any(_spans_overlap(custom_span, existing) for existing in presidio_spans):
            merged.append(custom_span)
    return merged
