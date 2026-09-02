from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from meridian.ingestion.local_files.note_parser import ParsedNote

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    path         TEXT PRIMARY KEY,
    content_text TEXT,
    content_hash TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    mtime_ns     INTEGER NOT NULL,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    fetched_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dead_letters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT,
    error       TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class NotesStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_note(self, note: ParsedNote) -> None:
        now = _now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO notes (
                    path, content_text, content_hash, size_bytes, mtime_ns,
                    is_deleted, fetched_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    content_text = excluded.content_text,
                    content_hash = excluded.content_hash,
                    size_bytes = excluded.size_bytes,
                    mtime_ns = excluded.mtime_ns,
                    is_deleted = 0,
                    updated_at = excluded.updated_at
                """,
                (
                    note.path,
                    note.content_text,
                    note.content_hash,
                    note.size_bytes,
                    note.mtime_ns,
                    now,
                    now,
                ),
            )

    def get_note_metadata(self, path: str) -> tuple[int, int] | None:
        row = self._conn.execute(
            "SELECT size_bytes, mtime_ns FROM notes WHERE path = ? AND is_deleted = 0", (path,)
        ).fetchone()
        if row is None:
            return None
        return row["size_bytes"], row["mtime_ns"]

    def mark_deleted(self, path: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE notes SET is_deleted = 1, updated_at = ? WHERE path = ?",
                (_now(), path),
            )

    def record_dead_letter(self, path: str, error: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO dead_letters (path, error, occurred_at) VALUES (?, ?, ?)",
                (path, error, _now()),
            )
