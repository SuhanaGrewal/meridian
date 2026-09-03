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


def _split_oversized(atom: str, max_size: int) -> list[str]:
    """fixed-size fallback split for a single atom still over max_size on
    its own (a run-on block with no natural break) - an absolute last resort."""
    return [atom[i : i + max_size] for i in range(0, len(atom), max_size)]


def _atomize(text: str, max_size: int) -> list[str]:
    """breaks text into pieces no larger than max_size, preferring natural
    boundaries: paragraphs, then sentences within an oversized paragraph,
    then a fixed-size cut as an absolute last resort."""
    atoms: list[str] = []
    for paragraph in split_into_paragraphs(text):
        if len(paragraph) <= max_size:
            atoms.append(paragraph)
            continue
        for sentence in split_into_sentences(paragraph):
            if len(sentence) <= max_size:
                atoms.append(sentence)
            else:
                atoms.extend(_split_oversized(sentence, max_size))
    return atoms


def pack_into_windows(text: str, *, target_size: int, overlap: int = 0) -> list[str]:
    """greedily packs text into windows up to target_size, carrying the
    trailing `overlap` characters of one window into the start of the next
    so an idea sitting near a cut point isn't split across both halves.

    used both for grouping sections into parent windows (overlap=0 - parents
    don't need it) and for splitting a window into child chunks for
    embedding (overlap=CHILD_OVERLAP_CHARS)."""
    atoms = _atomize(text, target_size)
    if not atoms:
        return []

    windows: list[str] = []
    current = atoms[0]
    for atom in atoms[1:]:
        candidate = f"{current} {atom}"
        if len(candidate) <= target_size:
            current = candidate
        else:
            windows.append(current)
            carry = current[-overlap:].strip() if overlap else ""
            current = f"{carry} {atom}".strip() if carry else atom
    windows.append(current)

    return windows
