from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from meridian.ingestion.calendar.event_parser import ParsedEvent

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


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class CalendarStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_event(self, event: ParsedEvent) -> None:
        now = _now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO events (
                    calendar_id, event_id, ical_uid, recurring_event_id, summary,
                    description, location, status, start_at, end_at, is_all_day,
                    organizer_email, attendees, source_updated_at, is_deleted,
                    fetched_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(calendar_id, event_id) DO UPDATE SET
                    ical_uid = excluded.ical_uid,
                    recurring_event_id = excluded.recurring_event_id,
                    summary = excluded.summary,
                    description = excluded.description,
                    location = excluded.location,
                    status = excluded.status,
                    start_at = excluded.start_at,
                    end_at = excluded.end_at,
                    is_all_day = excluded.is_all_day,
                    organizer_email = excluded.organizer_email,
                    attendees = excluded.attendees,
                    source_updated_at = excluded.source_updated_at,
                    is_deleted = 0,
                    updated_at = excluded.updated_at
                """,
                (
                    event.calendar_id,
                    event.event_id,
                    event.ical_uid,
                    event.recurring_event_id,
                    event.summary,
                    event.description,
                    event.location,
                    event.status,
                    event.start_at,
                    event.end_at,
                    int(event.is_all_day),
                    event.organizer_email,
                    json.dumps(event.attendees),
                    event.source_updated_at,
                    now,
                    now,
                ),
            )

    def get_event_row(self, calendar_id: str, event_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM events WHERE calendar_id = ? AND event_id = ?",
            (calendar_id, event_id),
        ).fetchone()

    def count_events(self, calendar_id: str | None = None) -> int:
        if calendar_id is None:
            return self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE calendar_id = ?", (calendar_id,)
        ).fetchone()[0]
