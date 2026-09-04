from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id     TEXT PRIMARY KEY,
    entity_type   TEXT NOT NULL,
    identity_key  TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    email         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);

CREATE TABLE IF NOT EXISTS entity_mentions (
    mention_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id      TEXT NOT NULL,
    source         TEXT NOT NULL,
    source_item_id TEXT NOT NULL,
    chunk_id       TEXT,
    surface_text   TEXT NOT NULL,
    mention_kind   TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
);
CREATE INDEX IF NOT EXISTS idx_mentions_entity_source ON entity_mentions(entity_id, source);
CREATE INDEX IF NOT EXISTS idx_mentions_source_item ON entity_mentions(source, source_item_id);

CREATE TABLE IF NOT EXISTS processed_items (
    source          TEXT NOT NULL,
    source_item_id  TEXT NOT NULL,
    phase           TEXT NOT NULL,
    change_signal   TEXT NOT NULL,
    processed_at    TEXT NOT NULL,
    PRIMARY KEY (source, source_item_id, phase)
);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class EntityGraphStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_entity(
        self,
        entity_id: str,
        entity_type: str,
        identity_key: str,
        display_name: str,
        email: str | None = None,
    ) -> bool:
        """creates or updates an entity, returning True if it's new. an
        already-known email is never erased by a later upsert that doesn't
        carry one (COALESCE keeps the existing value)."""
        created = self.get_entity(entity_id) is None
        now = _now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO entities (
                    entity_id, entity_type, identity_key, display_name, email, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    email = COALESCE(entities.email, excluded.email),
                    updated_at = excluded.updated_at
                """,
                (entity_id, entity_type, identity_key, display_name, email, now, now),
            )
        return created

    def get_entity(self, entity_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM entities WHERE entity_id = ?", (entity_id,)
        ).fetchone()

    def list_person_entities_with_email(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM entities WHERE entity_type = 'PERSON' AND email IS NOT NULL"
        ).fetchall()

    def add_mention(
        self,
        entity_id: str,
        source: str,
        source_item_id: str,
        chunk_id: str | None,
        surface_text: str,
        mention_kind: str,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO entity_mentions (
                    entity_id, source, source_item_id, chunk_id, surface_text, mention_kind, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (entity_id, source, source_item_id, chunk_id, surface_text, mention_kind, _now()),
            )

    def delete_mentions_for_item(self, source: str, source_item_id: str, mention_kind: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM entity_mentions WHERE source = ? AND source_item_id = ? AND mention_kind = ?",
                (source, source_item_id, mention_kind),
            )

    def get_change_signal(self, source: str, source_item_id: str, phase: str) -> str | None:
        row = self._conn.execute(
            "SELECT change_signal FROM processed_items WHERE source = ? AND source_item_id = ? AND phase = ?",
            (source, source_item_id, phase),
        ).fetchone()
        return row["change_signal"] if row else None

    def set_processed(self, source: str, source_item_id: str, phase: str, change_signal: str) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO processed_items (source, source_item_id, phase, change_signal, processed_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source, source_item_id, phase) DO UPDATE SET
                    change_signal = excluded.change_signal,
                    processed_at = excluded.processed_at
                """,
                (source, source_item_id, phase, change_signal, _now()),
            )

    def get_processed_item_ids(self, source: str, phase: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT source_item_id FROM processed_items WHERE source = ? AND phase = ?",
            (source, phase),
        ).fetchall()
        return {row["source_item_id"] for row in rows}

    def clear_processed(self, source: str, source_item_id: str, phase: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM processed_items WHERE source = ? AND source_item_id = ? AND phase = ?",
                (source, source_item_id, phase),
            )

    def count_entities(self, entity_type: str | None = None) -> int:
        if entity_type is None:
            return self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        return self._conn.execute(
            "SELECT COUNT(*) FROM entities WHERE entity_type = ?", (entity_type,)
        ).fetchone()[0]

    def count_mentions(self, mention_kind: str | None = None) -> int:
        if mention_kind is None:
            return self._conn.execute("SELECT COUNT(*) FROM entity_mentions").fetchone()[0]
        return self._conn.execute(
            "SELECT COUNT(*) FROM entity_mentions WHERE mention_kind = ?", (mention_kind,)
        ).fetchone()[0]

    def count_cross_source_entities(self) -> int:
        return self._conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT entity_id FROM entity_mentions
                GROUP BY entity_id HAVING COUNT(DISTINCT source) > 1
            )
            """
        ).fetchone()[0]
