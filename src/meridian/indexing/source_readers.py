from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceItem:
    item_id: str
    text: str
    has_headings: bool
    change_signal: str
    metadata: dict


def _readonly_connection(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def read_gmail_items(db_path: Path) -> list[SourceItem]:
    conn = _readonly_connection(db_path)
    if conn is None:
        return []

    try:
        rows = conn.execute(
            "SELECT message_id, subject, sender, sent_at, body_text, content_hash "
            "FROM messages WHERE is_deleted = 0"
        ).fetchall()
    finally:
        conn.close()

    items = []
    for row in rows:
        subject = row["subject"] or ""
        body = row["body_text"] or ""
        text = f"{subject}\n\n{body}".strip()
        items.append(
            SourceItem(
                item_id=row["message_id"],
                text=text,
                has_headings=False,
                change_signal=row["content_hash"],
                metadata={
                    "subject": subject,
                    "sender": row["sender"] or "",
                    "sent_at": row["sent_at"] or "",
                },
            )
        )
    return items


def read_calendar_items(db_path: Path) -> list[SourceItem]:
    conn = _readonly_connection(db_path)
    if conn is None:
        return []

    try:
        rows = conn.execute(
            "SELECT calendar_id, event_id, summary, description, location, "
            "start_at, source_updated_at FROM events WHERE is_deleted = 0"
        ).fetchall()
    finally:
        conn.close()

    items = []
    for row in rows:
        fields = [row["summary"], row["description"], row["location"]]
        text = "\n".join(f for f in fields if f).strip()
        items.append(
            SourceItem(
                item_id=f"{row['calendar_id']}:{row['event_id']}",
                text=text,
                has_headings=False,
                change_signal=row["source_updated_at"] or "",
                metadata={
                    "summary": row["summary"] or "",
                    "start_at": row["start_at"] or "",
                    "calendar_id": row["calendar_id"],
                },
            )
        )
    return items


def read_docs_items(db_path: Path) -> list[SourceItem]:
    conn = _readonly_connection(db_path)
    if conn is None:
        return []

    try:
        rows = conn.execute(
            "SELECT doc_id, title, content_text, content_hash FROM documents WHERE is_trashed = 0"
        ).fetchall()
    finally:
        conn.close()

    items = []
    for row in rows:
        title = row["title"] or ""
        content = row["content_text"] or ""
        # the title is prepended as its own heading line so it becomes the
        # doc's first section - titles are often the single most relevant
        # piece of text for search, worth including even though the
        # original design only mentioned content_text.
        text = f"# {title}\n\n{content}".strip() if title else content.strip()
        items.append(
            SourceItem(
                item_id=row["doc_id"],
                text=text,
                has_headings=True,
                change_signal=row["content_hash"],
                metadata={"title": title},
            )
        )
    return items


def read_local_files_items(db_path: Path) -> list[SourceItem]:
    conn = _readonly_connection(db_path)
    if conn is None:
        return []

    try:
        rows = conn.execute(
            "SELECT path, content_text, content_hash FROM notes WHERE is_deleted = 0"
        ).fetchall()
    finally:
        conn.close()

    items = []
    for row in rows:
        text = (row["content_text"] or "").strip()
        items.append(
            SourceItem(
                item_id=row["path"],
                text=text,
                has_headings=False,
                change_signal=row["content_hash"],
                metadata={"path": row["path"]},
            )
        )
    return items
