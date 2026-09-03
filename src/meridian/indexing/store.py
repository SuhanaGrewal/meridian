from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from meridian.indexing.parent_child import ChunkRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id        TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    source_item_id  TEXT NOT NULL,
    position        INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    parent_text     TEXT NOT NULL,
    is_own_parent   INTEGER NOT NULL,
    embedding       BLOB NOT NULL,
    metadata_json   TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_source_item ON chunks(source, source_item_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_text, content='chunks', content_rowid='rowid'
);

CREATE TABLE IF NOT EXISTS indexed_items (
    source          TEXT NOT NULL,
    source_item_id  TEXT NOT NULL,
    change_signal   TEXT NOT NULL,
    indexed_at      TEXT NOT NULL,
    PRIMARY KEY (source, source_item_id)
);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class IndexStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @property
    def connection(self) -> sqlite3.Connection:
        """exposes the underlying connection for keyword_search's raw FTS5
        queries, rather than having callers reach into a private attribute."""
        return self._conn

    def _delete_chunks_for_item(self, source: str, source_item_id: str) -> None:
        rowids = [
            row["rowid"]
            for row in self._conn.execute(
                "SELECT rowid FROM chunks WHERE source = ? AND source_item_id = ?",
                (source, source_item_id),
            )
        ]
        for rowid in rowids:
            self._conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (rowid,))
        self._conn.execute(
            "DELETE FROM chunks WHERE source = ? AND source_item_id = ?", (source, source_item_id)
        )

    def upsert_item_chunks(
        self,
        source: str,
        source_item_id: str,
        records: list[ChunkRecord],
        embeddings: list[np.ndarray],
        metadata: dict,
    ) -> None:
        """replaces all chunks for this source item with the given records -
        simplest correct way to handle the chunk count changing between
        versions of the same item."""
        now = _now()
        metadata_json = json.dumps(metadata)
        with self._conn:
            self._delete_chunks_for_item(source, source_item_id)
            for record, embedding in zip(records, embeddings):
                chunk_id = f"{source}:{source_item_id}:{record.position:04d}"
                cursor = self._conn.execute(
                    """
                    INSERT INTO chunks (
                        chunk_id, source, source_item_id, position, chunk_text,
                        parent_text, is_own_parent, embedding, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        source,
                        source_item_id,
                        record.position,
                        record.text,
                        record.parent_text,
                        int(record.is_own_parent),
                        np.asarray(embedding, dtype=np.float32).tobytes(),
                        metadata_json,
                        now,
                    ),
                )
                self._conn.execute(
                    "INSERT INTO chunks_fts (rowid, chunk_text) VALUES (?, ?)",
                    (cursor.lastrowid, record.text),
                )

    def get_chunks_with_embeddings(self, source: str | None = None) -> list[sqlite3.Row]:
        if source is None:
            return self._conn.execute("SELECT * FROM chunks").fetchall()
        return self._conn.execute("SELECT * FROM chunks WHERE source = ?", (source,)).fetchall()

    def get_chunk_row(self, chunk_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()

    def count_chunks(self, source: str | None = None) -> int:
        if source is None:
            return self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return self._conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE source = ?", (source,)
        ).fetchone()[0]

    def delete_item(self, source: str, source_item_id: str) -> None:
        """removes an item's chunks, fts entries, and change-signal record -
        one store, one delete path, no second system to keep in sync."""
        with self._conn:
            self._delete_chunks_for_item(source, source_item_id)
            self._conn.execute(
                "DELETE FROM indexed_items WHERE source = ? AND source_item_id = ?",
                (source, source_item_id),
            )

    def get_change_signal(self, source: str, source_item_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT change_signal FROM indexed_items WHERE source = ? AND source_item_id = ?",
            (source, source_item_id),
        ).fetchone()
        return row["change_signal"] if row else None

    def set_indexed(self, source: str, source_item_id: str, change_signal: str) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO indexed_items (source, source_item_id, change_signal, indexed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source, source_item_id) DO UPDATE SET
                    change_signal = excluded.change_signal,
                    indexed_at = excluded.indexed_at
                """,
                (source, source_item_id, change_signal, _now()),
            )
