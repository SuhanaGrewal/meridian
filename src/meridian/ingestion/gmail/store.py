from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from meridian.ingestion.gmail.message_parser import ParsedMessage

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    message_id   TEXT PRIMARY KEY,
    thread_id    TEXT NOT NULL,
    subject      TEXT,
    sender       TEXT,
    recipients   TEXT NOT NULL,
    sent_at      TEXT,
    body_text    TEXT,
    label_ids    TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    fetched_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    last_history_id TEXT,
    last_synced_at  TEXT
);

CREATE TABLE IF NOT EXISTS dead_letters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  TEXT,
    error       TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class SyncState:
    last_history_id: str | None
    last_synced_at: str | None


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class GmailStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_message(self, message: ParsedMessage) -> None:
        now = _now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO messages (
                    message_id, thread_id, subject, sender, recipients, sent_at,
                    body_text, label_ids, content_hash, is_deleted, fetched_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    subject = excluded.subject,
                    sender = excluded.sender,
                    recipients = excluded.recipients,
                    sent_at = excluded.sent_at,
                    body_text = excluded.body_text,
                    label_ids = excluded.label_ids,
                    content_hash = excluded.content_hash,
                    is_deleted = 0,
                    updated_at = excluded.updated_at
                """,
                (
                    message.message_id,
                    message.thread_id,
                    message.subject,
                    message.sender,
                    json.dumps(message.recipients),
                    message.sent_at,
                    message.body_text,
                    json.dumps(message.label_ids),
                    message.content_hash,
                    now,
                    now,
                ),
            )

    def update_labels(self, message_id: str, label_ids: list[str]) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE messages SET label_ids = ?, updated_at = ? WHERE message_id = ?",
                (json.dumps(label_ids), _now(), message_id),
            )

    def mark_deleted(self, message_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE messages SET is_deleted = 1, updated_at = ? WHERE message_id = ?",
                (_now(), message_id),
            )

    def record_dead_letter(self, message_id: str | None, error: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO dead_letters (message_id, error, occurred_at) VALUES (?, ?, ?)",
                (message_id, error, _now()),
            )

    def get_sync_state(self) -> SyncState:
        row = self._conn.execute(
            "SELECT last_history_id, last_synced_at FROM sync_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return SyncState(last_history_id=None, last_synced_at=None)
        return SyncState(last_history_id=row["last_history_id"], last_synced_at=row["last_synced_at"])

    def set_sync_state(self, last_history_id: str) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO sync_state (id, last_history_id, last_synced_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_history_id = excluded.last_history_id,
                    last_synced_at = excluded.last_synced_at
                """,
                (last_history_id, _now()),
            )

    def clear_sync_state(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM sync_state WHERE id = 1")

    def get_message_row(self, message_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM messages WHERE message_id = ?", (message_id,)
        ).fetchone()

    def count_messages(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    def get_all_messages(self) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM messages WHERE is_deleted = 0").fetchall()

    def list_messages_since(self, since: str) -> list[sqlite3.Row]:
        """filters on sent_at (the message's real send date), not
        updated_at (when this row was last written locally) - otherwise
        every message ever ingested would look "new" for 24h after any
        full backfill, since a backfill sets updated_at to the sync time
        regardless of how old the message actually is."""
        return self._conn.execute(
            "SELECT * FROM messages WHERE sent_at >= ? AND is_deleted = 0 ORDER BY sent_at",
            (since,),
        ).fetchall()
