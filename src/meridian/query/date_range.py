from __future__ import annotations

import re
from datetime import datetime, timedelta

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


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

    if re.search(r"\blast month\b", text):
        this_month_start = _start_of_month(now)
        return _add_months(this_month_start, -1), this_month_start

    if re.search(r"\bthis month\b", text):
        start = _start_of_month(now)
        return start, _add_months(start, 1)

    if re.search(r"\blast year\b", text):
        this_year_start = _start_of_year(now)
        return this_year_start.replace(year=this_year_start.year - 1), this_year_start

    if re.search(r"\bthis year\b", text):
        start = _start_of_year(now)
        return start, start.replace(year=start.year + 1)

    match = re.search(r"\blast (\d+) days?\b", text)
    if match:
        days = int(match.group(1))
        end = _start_of_day(now) + timedelta(days=1)
        # window covers `days` calendar days total, including today
        return end - timedelta(days=days), end

    for index, weekday_name in enumerate(_WEEKDAYS):
        if re.search(rf"\blast {weekday_name}\b", text):
            start = _most_recent_weekday(now, index) - timedelta(days=7)
            return start, start + timedelta(days=1)

    for index, weekday_name in enumerate(_WEEKDAYS):
        if re.search(rf"\b{weekday_name}\b", text):
            start = _most_recent_weekday(now, index)
            return start, start + timedelta(days=1)

    return None
