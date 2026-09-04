from datetime import datetime, timezone

from meridian.query.date_range import extract_date_range

# a fixed wednesday for deterministic tests
_NOW = datetime(2024, 6, 12, 15, 30, tzinfo=timezone.utc)  # 2024-06-12 is a Wednesday


def test_today():
    start, end = extract_date_range("what happened today", now=_NOW)

    assert start == datetime(2024, 6, 12, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 13, tzinfo=timezone.utc)


def test_yesterday():
    start, end = extract_date_range("what did I discuss yesterday", now=_NOW)

    assert start == datetime(2024, 6, 11, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 12, tzinfo=timezone.utc)


def test_this_week_monday_start():
    start, end = extract_date_range("meetings this week", now=_NOW)

    assert start == datetime(2024, 6, 10, tzinfo=timezone.utc)  # Monday
    assert end == datetime(2024, 6, 17, tzinfo=timezone.utc)


def test_last_week():
    start, end = extract_date_range("emails from last week", now=_NOW)

    assert start == datetime(2024, 6, 3, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 10, tzinfo=timezone.utc)


def test_this_month():
    start, end = extract_date_range("notes from this month", now=_NOW)

    assert start == datetime(2024, 6, 1, tzinfo=timezone.utc)
    assert end == datetime(2024, 7, 1, tzinfo=timezone.utc)


def test_last_month():
    start, end = extract_date_range("what happened last month", now=_NOW)

    assert start == datetime(2024, 5, 1, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_last_month_handles_year_rollover():
    now = datetime(2024, 1, 15, tzinfo=timezone.utc)

    start, end = extract_date_range("last month", now=now)

    assert start == datetime(2023, 12, 1, tzinfo=timezone.utc)
    assert end == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_this_year():
    start, end = extract_date_range("summary of this year", now=_NOW)

    assert start == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_last_year():
    start, end = extract_date_range("what happened last year", now=_NOW)

    assert start == datetime(2023, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_last_n_days_includes_today():
    start, end = extract_date_range("emails from the last 3 days", now=_NOW)

    assert start == datetime(2024, 6, 10, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 13, tzinfo=timezone.utc)
    assert (end - start).days == 3


def test_bare_weekday_is_most_recent_occurrence_including_today():
    # _NOW is a wednesday
    start, end = extract_date_range("meeting on wednesday", now=_NOW)

    assert start == datetime(2024, 6, 12, tzinfo=timezone.utc)  # today
    assert end == datetime(2024, 6, 13, tzinfo=timezone.utc)


def test_bare_weekday_before_today_in_same_week():
    start, end = extract_date_range("meeting on monday", now=_NOW)

    assert start == datetime(2024, 6, 10, tzinfo=timezone.utc)


def test_last_weekday_means_previous_calendar_week():
    # bare "monday" would be 2024-06-10 (this week); "last monday" should be
    # the monday before that, in the previous calendar week
    start, end = extract_date_range("meeting last monday", now=_NOW)

    assert start == datetime(2024, 6, 3, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 4, tzinfo=timezone.utc)


def test_unrecognized_phrase_returns_none():
    assert extract_date_range("what's my sister's favorite color", now=_NOW) is None


def test_no_time_reference_returns_none():
    assert extract_date_range("what's John's email address", now=_NOW) is None
