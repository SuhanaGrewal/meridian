from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

_DEFAULT_LOOKAHEAD_DAYS = 7
_DEFAULT_DURATION = timedelta(minutes=30)
_DEFAULT_BUSINESS_START_HOUR = 9
_DEFAULT_BUSINESS_END_HOUR = 17


def _free_slot_in_window(
    window_start: datetime, window_end: datetime, busy: list[tuple[datetime, datetime]], duration: timedelta
) -> tuple[datetime, datetime] | None:
    cursor = window_start
    for busy_start, busy_end in busy:
        if busy_start > cursor and busy_start - cursor >= duration:
            return cursor, cursor + duration
        cursor = max(cursor, busy_end)
    if window_end - cursor >= duration:
        return cursor, cursor + duration
    return None


def propose_free_slot(
    calendar_store: Any,
    *,
    now: datetime,
    lookahead_days: int = _DEFAULT_LOOKAHEAD_DAYS,
    duration: timedelta = _DEFAULT_DURATION,
    business_start_hour: int = _DEFAULT_BUSINESS_START_HOUR,
    business_end_hour: int = _DEFAULT_BUSINESS_END_HOUR,
) -> tuple[datetime, datetime] | None:
    """finds the first open slot of at least `duration` on the user's own
    calendar, within business hours on weekdays, over the next
    `lookahead_days` days. Deterministic interval-scanning, not an LLM
    guess - this project keeps date/time arithmetic out of LLM hands
    wherever a reliable algorithm exists (the same lesson already applied
    in query/prompt.py's recency labeling and
    inbox_intelligence/deadlines.py's deadline resolution). Existing
    calendar events are the only busy blocks considered; this only
    proposes a slot, it never books one - there's no calendar-write path
    in this project to book it with anyway."""
    window_end = now + timedelta(days=lookahead_days)
    rows = calendar_store.list_events_upcoming(now.isoformat(), window_end.isoformat())
    busy = sorted(
        (datetime.fromisoformat(row["start_at"]), datetime.fromisoformat(row["end_at"]))
        for row in rows
        if row["start_at"] and row["end_at"] and not row["is_all_day"]
    )

    for day_offset in range(lookahead_days + 1):
        day = (now + timedelta(days=day_offset)).date()
        if day.weekday() >= 5:  # Saturday/Sunday
            continue

        day_start = datetime.combine(day, time(business_start_hour), tzinfo=now.tzinfo)
        day_end = datetime.combine(day, time(business_end_hour), tzinfo=now.tzinfo)
        if day == now.date():
            day_start = max(day_start, now)
        if day_start >= day_end:
            continue

        day_busy = [
            (max(busy_start, day_start), min(busy_end, day_end))
            for busy_start, busy_end in busy
            if busy_end > day_start and busy_start < day_end
        ]
        slot = _free_slot_in_window(day_start, day_end, day_busy, duration)
        if slot is not None:
            return slot

    return None
