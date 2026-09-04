from __future__ import annotations

import sqlite3
from dataclasses import dataclass
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


@dataclass(frozen=True)
class SyncState:
    page_token: str | None
    last_synced_at: str | None


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

    def get_sync_state(self) -> SyncState:
        row = self._conn.execute(
            "SELECT page_token, last_synced_at FROM sync_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return SyncState(page_token=None, last_synced_at=None)
        return SyncState(page_token=row["page_token"], last_synced_at=row["last_synced_at"])

    def set_sync_state(self, page_token: str) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO sync_state (id, page_token, last_synced_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    page_token = excluded.page_token,
                    last_synced_at = excluded.last_synced_at
                """,
                (page_token, _now()),
            )

    def clear_sync_state(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM sync_state WHERE id = 1")

    def list_doc_ids(self) -> set[str]:
        rows = self._conn.execute("SELECT doc_id FROM documents WHERE is_trashed = 0")
        return {row["doc_id"] for row in rows.fetchall()}

    def tombstone_missing(self, seen_doc_ids: set[str]) -> int:
        missing = self.list_doc_ids() - set(seen_doc_ids)
        for doc_id in missing:
            self.mark_trashed(doc_id)
        return len(missing)

    def get_document_row(self, doc_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()

    def count_documents(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def list_docs_modified_since(self, since: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM documents WHERE modified_time >= ? AND is_trashed = 0 ORDER BY modified_time",
            (since,),
        ).fetchall()
