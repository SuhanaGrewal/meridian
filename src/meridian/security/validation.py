from __future__ import annotations

from pathlib import Path

MAX_FIELD_CHARS = 200_000


def is_within_folder(path: Path, folder: Path) -> bool:
    """resolves both paths and checks containment - the only check that
    catches a symlink whose resolved target escapes the configured
    folder (rglob()/is_file() alone would silently follow it)."""
    resolved_folder = folder.resolve()
    resolved_path = path.resolve()
    return resolved_path == resolved_folder or resolved_folder in resolved_path.parents


def truncate_field(value: str, *, max_chars: int = MAX_FIELD_CHARS) -> str:
    """caps a free-text field so one pathological huge email/doc/note
    can't blow up memory or downstream tokenization. applied before any
    hashing/storage so change-detection hashes stay consistent with the
    capped content."""
    if len(value) <= max_chars:
        return value
    return value[:max_chars]
