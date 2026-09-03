from __future__ import annotations

import re

CHILD_CHUNK_CHARS = 300
CHILD_OVERLAP_CHARS = 50
PARENT_CHUNK_CHARS = 1500

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def split_into_paragraphs(text: str) -> list[str]:
    """splits on one-or-more blank lines. drops empty results."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def split_into_sentences(text: str) -> list[str]:
    """splits on sentence-ending punctuation followed by whitespace and a
    capital letter or digit - a light regex, no nlp model needed."""
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
