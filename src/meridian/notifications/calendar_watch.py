from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

_DEFAULT_LEAD_MINUTES = 15


@dataclass(frozen=True)
class UpcomingEvent:
    event_id: str
    summary: str
    start_at: str


def check_upcoming_events(
    calendar_store: Any,
    notification_store: Any,
    *,
    now: datetime,
    lead_minutes: int = _DEFAULT_LEAD_MINUTES,
) -> list[UpcomingEvent]:
    """finds events starting within the next `lead_minutes` that haven't
    already been notified about, and marks them notified before
    returning - so this is safe to call every minute (the intended launchd
    interval) without re-alerting on the same event across successive
    checks. Deliberately a one-shot check, not a long-running daemon: this
    project has no persistent-process infrastructure anywhere (every phase
    is a one-shot CLI invoked by launchd/cron), and a frequent scheduled
    check gets "close to real-time" without introducing process
    supervision, crash-restart, and log-rotation concerns a genuine daemon
    would need for a single-user personal tool. All-day events are
    excluded - "starts in 15 minutes" doesn't mean anything for them."""
    window_end = now + timedelta(minutes=lead_minutes)
    rows = calendar_store.list_events_upcoming(now.isoformat(), window_end.isoformat())

    newly_notified: list[UpcomingEvent] = []
    for row in rows:
        if row["is_all_day"]:
            continue
        event_id = f"{row['calendar_id']}:{row['event_id']}"
        if notification_store.has_notified(event_id):
            continue
        notification_store.mark_notified(event_id)
        newly_notified.append(UpcomingEvent(event_id=event_id, summary=row["summary"], start_at=row["start_at"]))

    return newly_notified
