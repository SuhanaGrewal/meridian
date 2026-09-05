from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    question_id   TEXT PRIMARY KEY,
    question_text TEXT NOT NULL,
    is_waiting    INTEGER NOT NULL,
    resolved      INTEGER NOT NULL DEFAULT 0,
    asked_at      TEXT NOT NULL,
    resolved_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_questions_open_waiting ON questions(is_waiting, resolved);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class QueryHistoryStore:
    """persists every question asked through query.__main__, tagged with
    whether it's the "waiting on something" kind (see query/history.py) -
    the only kind that ever gets checked for resolution and surfaced in a
    digest as an open follow-up (#9)."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add_question(self, question_text: str, *, is_waiting: bool, asked_at: str | None = None) -> str:
        question_id = str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO questions (question_id, question_text, is_waiting, resolved, asked_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (question_id, question_text, int(is_waiting), asked_at or _now()),
            )
        return question_id

    def mark_resolved(self, question_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE questions SET resolved = 1, resolved_at = ? WHERE question_id = ?",
                (_now(), question_id),
            )

    def get_question(self, question_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM questions WHERE question_id = ?", (question_id,)
        ).fetchone()

    def list_open_waiting_questions(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM questions WHERE is_waiting = 1 AND resolved = 0 ORDER BY asked_at"
        ).fetchall()

    def count_questions(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
