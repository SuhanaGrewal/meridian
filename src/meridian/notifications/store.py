from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notified_events (
    event_id     TEXT PRIMARY KEY,
    notified_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class NotificationStore:
    """dedupes calendar notifications (#12) across successive runs of the
    frequent (every-minute) check - without this, the same "meeting in 15
    minutes" alert would fire on every check between the lead time and the
    event's actual start."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def has_notified(self, event_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM notified_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None

    def mark_notified(self, event_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO notified_events (event_id, notified_at) VALUES (?, ?)",
                (event_id, _now()),
            )

    def count_notified(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM notified_events").fetchone()[0]
