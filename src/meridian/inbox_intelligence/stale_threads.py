from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

from meridian.query.date_range import parse_stored_date

# gmail's own category labels for mail that was never a real back-and-forth
# needing a reply - a newsletter or promo sitting unread for years isn't
# "waiting on you" in any meaningful sense. CATEGORY_PERSONAL and anything
# uncategorized (the primary inbox) are left alone.
_NON_ACTIONABLE_CATEGORIES = frozenset(
    {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_FORUMS"}
)

# an automated auto-reply/vacation-responder/bounce message isn't a human
# waiting on you either, even when it lands straight in the primary inbox
# (as visa/government auto-replies often do) - no CATEGORY_* label catches
# these, so this is a separate, subject/sender-based heuristic. Real
# auto-reply detection would use the RFC 3834 Auto-Submitted header, but
# gmail's ingestion doesn't currently capture raw headers beyond
# subject/from/to - this heuristic works on data already stored today.
_AUTO_REPLY_SUBJECT_RE = re.compile(
    r"\b(auto[- ]?reply|automatic reply|out[- ]of[- ]office|vacation (response|reply|responder)"
    r"|away from (my )?(desk|email|office)|delivery status notification|undeliverable)\b",
    re.IGNORECASE,
)
_AUTO_REPLY_SENDER_RE = re.compile(
    r"(no[-._]?reply|do[-._]?not[-._]?reply|auto[-._]?reply|mailer-daemon|postmaster)",
    re.IGNORECASE,
)


def _looks_like_auto_reply(subject: str, sender: str) -> bool:
    if _AUTO_REPLY_SUBJECT_RE.search(subject or ""):
        return True
    _, sender_email = parseaddr(sender or "")
    local_part = sender_email.split("@")[0] if sender_email else ""
    return bool(_AUTO_REPLY_SENDER_RE.search(local_part))


@dataclass(frozen=True)
class StaleThread:
    thread_id: str
    subject: str
    last_sender: str
    last_message_snippet: str
    last_message_at: str
    days_quiet: int


_SNIPPET_CHARS = 200


def find_stale_threads(
    gmail_store: Any,
    account_email: str,
    *,
    now: datetime | None = None,
    min_days_quiet: int = 3,
    max_days_quiet: int | None = None,
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
    multi-year-old threads that are functionally dead, not pending."""
    now = now if now is not None else datetime.now(tz=timezone.utc)
    account_email_lower = account_email.strip().lower()
    results: list[StaleThread] = []

    for row in gmail_store.list_latest_message_per_thread():
        _, sender_email = parseaddr(row["sender"] or "")
        if sender_email.lower() == account_email_lower:
            continue

        labels = set(json.loads(row["label_ids"] or "[]"))
        if labels & _NON_ACTIONABLE_CATEGORIES:
            continue

        if _looks_like_auto_reply(row["subject"], row["sender"]):
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
