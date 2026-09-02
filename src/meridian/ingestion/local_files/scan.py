from __future__ import annotations

from dataclasses import dataclass

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
