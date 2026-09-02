from __future__ import annotations

from dataclasses import dataclass


class NoteParseError(Exception):
    pass


@dataclass(frozen=True)
class ParsedNote:
    path: str
    content_text: str
    content_hash: str
    size_bytes: int
    mtime_ns: int
