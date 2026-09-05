from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    draft_id        TEXT PRIMARY KEY,
    thread_id       TEXT NOT NULL,
    message_id      TEXT NOT NULL,
    recipient_email TEXT,
    draft_text      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class DraftStore:
    """persists drafted replies (#11, drafting half only). "approved" here
    means "ready to send whenever sending is enabled" - it does not send
    anything. There is no send path anywhere in this codebase yet; that is
    deliberately a separate, not-yet-authorized piece of work (see
    BACKLOG.md #11) requiring a new Google OAuth scope this project
    doesn't have."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add_draft(
        self, thread_id: str, message_id: str, recipient_email: str | None, draft_text: str
    ) -> str:
        draft_id = str(uuid.uuid4())
        now = _now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO drafts (
                    draft_id, thread_id, message_id, recipient_email, draft_text, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (draft_id, thread_id, message_id, recipient_email, draft_text, now, now),
            )
        return draft_id

    def get_draft(self, draft_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()

    def get_draft_for_thread(self, thread_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM drafts WHERE thread_id = ? ORDER BY created_at DESC LIMIT 1", (thread_id,)
        ).fetchone()

    def update_draft_text(self, draft_id: str, new_text: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE drafts SET draft_text = ?, updated_at = ? WHERE draft_id = ?",
                (new_text, _now(), draft_id),
            )
        return cursor.rowcount > 0

    def _set_status(self, draft_id: str, status: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE drafts SET status = ?, updated_at = ? WHERE draft_id = ?",
                (status, _now(), draft_id),
            )
        return cursor.rowcount > 0

    def approve(self, draft_id: str) -> bool:
        return self._set_status(draft_id, "approved")

    def reject(self, draft_id: str) -> bool:
        return self._set_status(draft_id, "rejected")

    def list_pending_drafts(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM drafts WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()

    def count_drafts(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
