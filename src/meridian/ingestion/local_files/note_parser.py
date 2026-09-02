from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from meridian.common.retry import retry_with_backoff


class NoteParseError(Exception):
    pass


@dataclass(frozen=True)
class ParsedNote:
    path: str
    content_text: str
    content_hash: str
    size_bytes: int
    mtime_ns: int


def _read_file_bytes(path: Path, *, logger: logging.Logger | None = None) -> bytes:
    """reads a file's raw bytes, retrying on a transient OSError (e.g. the
    file being briefly locked/mid-write by another program)."""
    return retry_with_backoff(
        path.read_bytes,
        exceptions=(OSError,),
        max_attempts=3,
        base_delay=0.5,
        logger=logger,
        operation="local_files.read_file",
    )
