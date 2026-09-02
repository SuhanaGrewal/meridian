from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

DEFAULT_EXTENSIONS = {".txt", ".md"}


@dataclass
class ScanStats:
    files_scanned: int = 0
    notes_added: int = 0
    notes_updated: int = 0
    notes_skipped_unchanged: int = 0
    notes_deleted: int = 0
    parse_failures: int = 0
    duration_ms: float = 0.0


def _iter_note_files(notes_folder: Path, extensions: set[str]) -> Iterator[Path]:
    for path in sorted(notes_folder.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in extensions:
            continue

        relative_parts = path.relative_to(notes_folder).parts
        if any(part.startswith(".") for part in relative_parts):
            continue

        yield path
