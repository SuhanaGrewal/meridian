from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from meridian.ingestion.docs.doc_parser import ParsedDoc

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id        TEXT PRIMARY KEY,
    title         TEXT,
    content_text  TEXT,
    modified_time TEXT,
    content_hash  TEXT NOT NULL,
    is_trashed    INTEGER NOT NULL DEFAULT 0,
    fetched_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    page_token     TEXT,
    last_synced_at TEXT
);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class DocsStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_document(self, doc: ParsedDoc) -> None:
        now = _now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO documents (
                    doc_id, title, content_text, modified_time, content_hash,
                    is_trashed, fetched_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    title = excluded.title,
                    content_text = excluded.content_text,
                    modified_time = excluded.modified_time,
                    content_hash = excluded.content_hash,
                    is_trashed = 0,
                    updated_at = excluded.updated_at
                """,
                (
                    doc.doc_id,
                    doc.title,
                    doc.content_text,
                    doc.modified_time,
                    doc.content_hash,
                    now,
                    now,
                ),
            )

    def mark_trashed(self, doc_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE documents SET is_trashed = 1, updated_at = ? WHERE doc_id = ?",
                (_now(), doc_id),
            )

    def get_modified_time(self, doc_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT modified_time FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return row["modified_time"] if row else None
