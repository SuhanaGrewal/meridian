from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    reminder_id         TEXT PRIMARY KEY,
    reminder_text       TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
    proposed_slot_start TEXT,
    proposed_slot_end   TEXT,
    created_at          TEXT NOT NULL,
    decided_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class ReminderStore:
    """tracks imperative "remind me to..." intake (#10) - distinct from
    the query-history store (#9, plain questions) and every other store
    in this project's read-only design: nothing here ever gets acted on
    automatically. A reminder only ever carries a *proposed* free-calendar
    slot (see reminders/scheduling.py), never a booked one - there is no
    calendar-write path anywhere in this project to book it even if this
    store wanted to."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add_reminder(
        self, reminder_text: str, *, proposed_slot_start: str | None = None, proposed_slot_end: str | None = None
    ) -> str:
        reminder_id = str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO reminders (reminder_id, reminder_text, status, proposed_slot_start, proposed_slot_end, created_at)
                VALUES (?, ?, 'pending', ?, ?, ?)
                """,
                (reminder_id, reminder_text, proposed_slot_start, proposed_slot_end, _now()),
            )
        return reminder_id

    def get_reminder(self, reminder_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM reminders WHERE reminder_id = ?", (reminder_id,)
        ).fetchone()

    def dismiss(self, reminder_id: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE reminders SET status = 'dismissed', decided_at = ? WHERE reminder_id = ?",
                (_now(), reminder_id),
            )
        return cursor.rowcount > 0

    def list_pending_reminders(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM reminders WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()

    def count_reminders(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]
