from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

from meridian.inbox_intelligence.gmail_filters import NON_ACTIONABLE_CATEGORIES, looks_like_auto_reply
from meridian.query.date_range import parse_stored_date


@dataclass(frozen=True)
class StaleThread:
    thread_id: str
    subject: str
    last_sender: str
    last_message_snippet: str
    last_message_at: str
    days_quiet: int


_SNIPPET_CHARS = 500  # matches digest/gather.py's _DETAIL_CHARS - enough that a
# summarizer isn't fed a sentence cut off mid-word


def find_stale_threads(
    gmail_store: Any,
    account_email: str,
    *,
    now: datetime | None = None,
    min_days_quiet: int = 3,
    max_days_quiet: int | None = None,
    exclude_thread_ids: frozenset[str] = frozenset(),
) -> list[StaleThread]:
    """threads where the last message wasn't from the account owner and
    it's been quiet for at least min_days_quiet - i.e. "your move." A
    thread whose last message the account owner sent themselves is
    excluded outright, regardless of how long ago that was - it's not
    waiting on a reply from the user. Threads whose last message is a
    newsletter/promo/social/forum notification (per gmail's own category
    labels) or an automated auto-reply/bounce/vacation-responder message
    are excluded too - neither was ever actually waiting on a reply.
    max_days_quiet optionally caps how far
    back to look, since a mailbox's full history can surface
    multi-year-old threads that are functionally dead, not pending.
    exclude_thread_ids lets a caller hide threads the user already
    dismissed as handled (see InboxIntelligenceStore.list_dismissed_thread_ids)
    - dismissal is a caller concern, not something this pure function
    persists itself."""
    now = now if now is not None else datetime.now(tz=timezone.utc)
    account_email_lower = account_email.strip().lower()
    results: list[StaleThread] = []

    for row in gmail_store.list_latest_message_per_thread():
        if row["thread_id"] in exclude_thread_ids:
            continue

        _, sender_email = parseaddr(row["sender"] or "")
        if sender_email.lower() == account_email_lower:
            continue

        labels = set(json.loads(row["label_ids"] or "[]"))
        if labels & NON_ACTIONABLE_CATEGORIES:
            continue

        if looks_like_auto_reply(row["subject"], row["sender"]):
            continue

        sent_at = parse_stored_date(row["sent_at"])
        if sent_at is None:
            continue

        days_quiet = (now - sent_at).days
        if days_quiet < min_days_quiet:
            continue
        if max_days_quiet is not None and days_quiet > max_days_quiet:
            continue

        results.append(
            StaleThread(
                thread_id=row["thread_id"],
                subject=row["subject"] or "",
                last_sender=row["sender"] or "",
                last_message_snippet=(row["body_text"] or "")[:_SNIPPET_CHARS],
                last_message_at=row["sent_at"],
                days_quiet=days_quiet,
            )
        )

    return sorted(results, key=lambda thread: thread.days_quiet, reverse=True)
