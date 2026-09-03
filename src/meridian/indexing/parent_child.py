from __future__ import annotations

from dataclasses import dataclass

from meridian.indexing.chunking import (
    CHILD_CHUNK_CHARS,
    CHILD_OVERLAP_CHARS,
    PARENT_CHUNK_CHARS,
    pack_into_windows,
    split_into_sections,
)


@dataclass(frozen=True)
class ChunkRecord:
    text: str
    parent_text: str
    position: int
    is_own_parent: bool


def build_chunks(text: str, *, has_headings: bool = False) -> list[ChunkRecord]:
    """splits text into child chunks linked to parent context, per the
    parent/child design: parent = the immediate structural unit one level
    up from where a child was cut. if the whole item fits within one parent
    window, there's no real parent/child distinction - one chunk, its own
    parent."""
    text = text.strip()
    if not text:
        return []

    if len(text) <= PARENT_CHUNK_CHARS:
        return [ChunkRecord(text=text, parent_text=text, position=0, is_own_parent=True)]

    sections = split_into_sections(text) if has_headings else [text]

    parent_windows: list[str] = []
    for section in sections:
        parent_windows.extend(pack_into_windows(section, target_size=PARENT_CHUNK_CHARS))

    records: list[ChunkRecord] = []
    position = 0
    for parent_text in parent_windows:
        children = pack_into_windows(
            parent_text, target_size=CHILD_CHUNK_CHARS, overlap=CHILD_OVERLAP_CHARS
        )
        for child_text in children:
            records.append(
                ChunkRecord(text=child_text, parent_text=parent_text, position=position, is_own_parent=False)
            )
            position += 1

    return records
