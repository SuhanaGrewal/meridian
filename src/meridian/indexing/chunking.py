from __future__ import annotations

import re

CHILD_CHUNK_CHARS = 300
CHILD_OVERLAP_CHARS = 50
PARENT_CHUNK_CHARS = 1500

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)


def split_into_sections(text: str) -> list[str]:
    """splits on markdown-style heading lines (the '#'/'##' markers phase 4
    bakes into flattened doc content). each section is a heading line plus
    everything until the next heading, regardless of heading level - good
    enough for grouping into similarly-sized chunks without needing a full
    nested outline. text with no heading lines returns as a single section."""
    matches = list(_HEADING_LINE_RE.finditer(text))
    if not matches:
        return [text] if text.strip() else []

    sections = []
    leading = text[: matches[0].start()].strip()
    if leading:
        sections.append(leading)

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[match.start() : end].strip()
        if section:
            sections.append(section)

    return sections


def split_into_paragraphs(text: str) -> list[str]:
    """splits on one-or-more blank lines. drops empty results."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def split_into_sentences(text: str) -> list[str]:
    """splits on sentence-ending punctuation followed by whitespace and a
    capital letter or digit - a light regex, no nlp model needed."""
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
