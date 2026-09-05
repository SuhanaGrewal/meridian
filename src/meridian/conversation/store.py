from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    turn_id         TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_conversation ON turns(conversation_id, created_at);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class ConversationStore:
    """persists a text thread's turns so a follow-up question can be
    understood in context - the backend piece a future chat UI (#5) would
    call into, not the UI itself. Turns are stored as plain real text,
    the same text already shown to the user - never a redaction mapping
    (mappings are per-call and never persisted, per this project's
    redaction design; see query/answer.py's docstring). Each turn gets
    re-redacted fresh as part of one whole-prompt string on every call,
    exactly like every other external call in this project - no new
    redaction mechanism, just more text in the same one string."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add_turn(self, conversation_id: str, role: str, content: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO turns (turn_id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), conversation_id, role, content, _now()),
            )

    def list_turns(self, conversation_id: str, *, limit: int | None = None) -> list[sqlite3.Row]:
        """returns turns oldest-first. `limit`, when given, keeps only the
        most recent `limit` turns - a simple fixed-window bound on prompt
        growth, not a summarization strategy; a very long-running thread
        will lose its earliest context rather than the prompt growing
        without bound."""
        rows = self._conn.execute(
            "SELECT * FROM turns WHERE conversation_id = ? ORDER BY created_at", (conversation_id,)
        ).fetchall()
        if limit is not None and len(rows) > limit:
            rows = rows[-limit:]
        return rows

    def clear_conversation(self, conversation_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM turns WHERE conversation_id = ?", (conversation_id,))

    def count_turns(self, conversation_id: str | None = None) -> int:
        if conversation_id is None:
            return self._conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        return self._conn.execute(
            "SELECT COUNT(*) FROM turns WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()[0]
