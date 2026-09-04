from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS digest_runs (
    run_id       TEXT PRIMARY KEY,
    window_start TEXT NOT NULL,
    window_end   TEXT NOT NULL,
    digest_text  TEXT NOT NULL,
    sources_text TEXT NOT NULL,
    item_count   INTEGER NOT NULL DEFAULT 0,
    llm_used     INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'pending',
    generated_at TEXT NOT NULL,
    decided_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_digest_runs_status ON digest_runs(status);

CREATE TABLE IF NOT EXISTS digest_state (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    cursor_at TEXT
);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class DigestStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def create_run(
        self,
        run_id: str,
        window_start: str,
        window_end: str,
        digest_text: str,
        sources_text: str,
        item_count: int,
        llm_used: bool,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO digest_runs (
                    run_id, window_start, window_end, digest_text, sources_text,
                    item_count, llm_used, status, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    run_id,
                    window_start,
                    window_end,
                    digest_text,
                    sources_text,
                    item_count,
                    int(llm_used),
                    _now(),
                ),
            )

    def get_run(self, run_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM digest_runs WHERE run_id = ?", (run_id,)
        ).fetchone()

    def get_pending_run(self) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM digest_runs WHERE status = 'pending' ORDER BY generated_at LIMIT 1"
        ).fetchone()

    def list_pending_runs(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM digest_runs WHERE status = 'pending' ORDER BY generated_at"
        ).fetchall()

    def mark_approved(self, run_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE digest_runs SET status = 'approved', decided_at = ? WHERE run_id = ?",
                (_now(), run_id),
            )

    def mark_rejected(self, run_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE digest_runs SET status = 'rejected', decided_at = ? WHERE run_id = ?",
                (_now(), run_id),
            )

    def get_cursor(self) -> str | None:
        row = self._conn.execute("SELECT cursor_at FROM digest_state WHERE id = 1").fetchone()
        return row["cursor_at"] if row else None

    def set_cursor(self, cursor_at: str) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO digest_state (id, cursor_at) VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET cursor_at = excluded.cursor_at
                """,
                (cursor_at,),
            )

    def count_runs(self, status: str | None = None) -> int:
        if status is None:
            return self._conn.execute("SELECT COUNT(*) FROM digest_runs").fetchone()[0]
        return self._conn.execute(
            "SELECT COUNT(*) FROM digest_runs WHERE status = ?", (status,)
        ).fetchone()[0]
