from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

_SCHEMA = """
CREATE TABLE IF NOT EXISTS commitments (
    commitment_id   TEXT PRIMARY KEY,
    message_id      TEXT NOT NULL,
    thread_id       TEXT NOT NULL,
    made_by         TEXT NOT NULL,
    other_party     TEXT,
    description     TEXT NOT NULL,
    deadline_phrase TEXT,
    due_date        TEXT,
    is_resolved     INTEGER NOT NULL DEFAULT 0,
    detected_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scanned_messages (
    message_id TEXT PRIMARY KEY,
    scanned_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class Commitment:
    commitment_id: str
    message_id: str
    thread_id: str
    made_by: str
    other_party: str
    description: str
    deadline_phrase: str | None
    due_date: str | None
    is_resolved: bool
    detected_at: str


class CommitmentStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def is_message_scanned(self, message_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM scanned_messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        return row is not None

    def mark_message_scanned(self, message_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO scanned_messages (message_id, scanned_at) VALUES (?, ?)",
                (message_id, _now()),
            )

    def add_commitment(
        self,
        *,
        message_id: str,
        thread_id: str,
        made_by: str,
        other_party: str,
        description: str,
        deadline_phrase: str | None,
        due_date: str | None,
    ) -> str:
        commitment_id = str(uuid4())
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO commitments (
                    commitment_id, message_id, thread_id, made_by, other_party,
                    description, deadline_phrase, due_date, is_resolved, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    commitment_id, message_id, thread_id, made_by, other_party,
                    description, deadline_phrase, due_date, _now(),
                ),
            )
        return commitment_id

    def mark_resolved(self, commitment_id: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE commitments SET is_resolved = 1 WHERE commitment_id = ?", (commitment_id,)
            )
        return cursor.rowcount > 0

    def list_open_commitments(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM commitments WHERE is_resolved = 0 ORDER BY due_date IS NULL, due_date"
        ).fetchall()

    def count_scanned_messages(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM scanned_messages").fetchone()[0]
