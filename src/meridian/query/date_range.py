from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# which metadata key holds a usable date, per source - docs and local_files
# have no date field at all in their chunk metadata (per source_readers.py).
_DATE_METADATA_KEYS = {"gmail": "sent_at", "calendar": "start_at"}


def _start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_week(dt: datetime) -> datetime:
    return _start_of_day(dt) - timedelta(days=dt.weekday())


def _start_of_month(dt: datetime) -> datetime:
    return _start_of_day(dt).replace(day=1)


def _add_months(dt: datetime, months: int) -> datetime:
    total = dt.month - 1 + months
    year = dt.year + total // 12
    month = total % 12 + 1
    return dt.replace(year=year, month=month)


def _start_of_year(dt: datetime) -> datetime:
    return _start_of_day(dt).replace(month=1, day=1)


def _most_recent_weekday(now: datetime, target_weekday: int) -> datetime:
    days_back = (now.weekday() - target_weekday) % 7
    return _start_of_day(now) - timedelta(days=days_back)


def extract_date_range(question: str, *, now: datetime) -> tuple[datetime, datetime] | None:
    """extracts a [start, end) date range from a relative time phrase in the
    question. `now` is always injected, never read internally, for full
    testability. returns None (never raises) when no recognized phrase is
    found - an unrecognized time reference should never block a query, it
    just means no date filter gets applied."""
    text = question.lower()

    if re.search(r"\btoday\b", text):
        start = _start_of_day(now)
        return start, start + timedelta(days=1)

    if re.search(r"\byesterday\b", text):
        start = _start_of_day(now) - timedelta(days=1)
        return start, start + timedelta(days=1)

    if re.search(r"\blast week\b", text):
        this_week_start = _start_of_week(now)
        return this_week_start - timedelta(days=7), this_week_start

    if re.search(r"\bthis week\b", text):
        start = _start_of_week(now)
        return start, start + timedelta(days=7)

    if re.search(r"\bnext week\b", text):
        start = _start_of_week(now) + timedelta(days=7)
        return start, start + timedelta(days=7)

    if re.search(r"\blast month\b", text):
        this_month_start = _start_of_month(now)
        return _add_months(this_month_start, -1), this_month_start

    if re.search(r"\bthis month\b", text):
        start = _start_of_month(now)
        return start, _add_months(start, 1)

    if re.search(r"\bnext month\b", text):
        start = _add_months(_start_of_month(now), 1)
        return start, _add_months(start, 1)

    if re.search(r"\blast year\b", text):
        this_year_start = _start_of_year(now)
        return this_year_start.replace(year=this_year_start.year - 1), this_year_start

    if re.search(r"\bthis year\b", text):
        start = _start_of_year(now)
        return start, start.replace(year=start.year + 1)

    if re.search(r"\bnext year\b", text):
        start = _start_of_year(now).replace(year=now.year + 1)
        return start, start.replace(year=start.year + 1)

    match = re.search(r"\blast (\d+) days?\b", text)
    if match:
        days = int(match.group(1))
        end = _start_of_day(now) + timedelta(days=1)
        # window covers `days` calendar days total, including today
        return end - timedelta(days=days), end

    match = re.search(r"\bnext (\d+) days?\b", text)
    if match:
        days = int(match.group(1))
        start = _start_of_day(now)
        # window covers `days` calendar days total, starting today - the
        # forward-looking mirror of "last N days" above
        return start, start + timedelta(days=days)

    for index, weekday_name in enumerate(_WEEKDAYS):
        if re.search(rf"\blast {weekday_name}\b", text):
            start = _most_recent_weekday(now, index) - timedelta(days=7)
            return start, start + timedelta(days=1)

    for index, weekday_name in enumerate(_WEEKDAYS):
        if re.search(rf"\bnext {weekday_name}\b", text):
            # the *next* occurrence strictly ahead: if today is that
            # weekday, "next monday" means 7 days from now, not today.
            start = _most_recent_weekday(now, index) + timedelta(days=7)
            return start, start + timedelta(days=1)

    for index, weekday_name in enumerate(_WEEKDAYS):
        if re.search(rf"\b{weekday_name}\b", text):
            start = _most_recent_weekday(now, index)
            return start, start + timedelta(days=1)

    if re.search(r"\bupcoming\b", text):
        # no more specific horizon given - a reasonable default forward
        # window, same philosophy as query/router.py's _DEFAULT_MAX_DAYS_QUIET
        start = _start_of_day(now)
        return start, start + timedelta(days=30)

    return None


def is_forward_looking_range(date_range: tuple[datetime, datetime], *, now: datetime) -> bool:
    """true for a range that only reaches into the present/future (e.g.
    "next week," "upcoming," "next Friday," bare "today") - the phrases
    for which finding nothing should trigger a fallback to the most
    recent past match rather than just abstaining outright (see
    answer.py::ask()). False for a range anchored in the past (e.g. "last
    week," "this month," a bare weekday name resolving to its most recent
    past occurrence), where surfacing an unrelated past item as a
    substitute wouldn't make sense - the user already knows they're
    asking about the past."""
    start, _ = date_range
    return start >= _start_of_day(now)


def parse_stored_date(value: str | None) -> datetime | None:
    """parses an iso8601 string (full datetime or a bare date) into an
    aware datetime. returns None for anything missing or unparseable,
    rather than raising - a malformed stored date should never crash a
    query, just be treated as unknown."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def chunk_in_range(
    source: str, metadata: dict, date_range: tuple[datetime, datetime] | None
) -> bool:
    """checks whether a chunk's stored date falls within date_range.

    fails open (returns True, i.e. "keep it") whenever there's no date
    filter active, the source has no date concept at all (docs,
    local_files), or the stored value is missing/unparseable - there's no
    correct way to include-or-exclude an item by date when no usable date
    exists, so excluding it would just be silently, incorrectly dropping
    content a user might need."""
    if date_range is None:
        return True

    metadata_key = _DATE_METADATA_KEYS.get(source)
    if metadata_key is None:
        return True

    parsed = parse_stored_date(metadata.get(metadata_key))
    if parsed is None:
        return True

    start, end = date_range
    return start <= parsed < end
