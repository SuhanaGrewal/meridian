from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    calendar_id        TEXT NOT NULL,
    event_id           TEXT NOT NULL,
    ical_uid           TEXT,
    recurring_event_id TEXT,
    summary            TEXT,
    description        TEXT,
    location           TEXT,
    status             TEXT NOT NULL,
    start_at           TEXT,
    end_at             TEXT,
    is_all_day         INTEGER NOT NULL DEFAULT 0,
    organizer_email    TEXT,
    attendees          TEXT NOT NULL,
    source_updated_at  TEXT,
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    fetched_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    PRIMARY KEY (calendar_id, event_id)
);

CREATE TABLE IF NOT EXISTS sync_state (
    calendar_id    TEXT PRIMARY KEY,
    sync_token     TEXT,
    last_synced_at TEXT
);
"""


class CalendarStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
