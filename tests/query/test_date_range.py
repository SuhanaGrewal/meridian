from datetime import datetime, timezone

from meridian.query.date_range import chunk_in_range, extract_date_range, parse_stored_date

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


def test_next_week():
    start, end = extract_date_range("what's on my calendar next week", now=_NOW)

    assert start == datetime(2024, 6, 17, tzinfo=timezone.utc)  # monday after this week
    assert end == datetime(2024, 6, 24, tzinfo=timezone.utc)


def test_last_month():
    start, end = extract_date_range("what happened last month", now=_NOW)

    assert start == datetime(2024, 5, 1, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_last_month_handles_year_rollover():
    now = datetime(2024, 1, 15, tzinfo=timezone.utc)

    start, end = extract_date_range("last month", now=now)

    assert start == datetime(2023, 12, 1, tzinfo=timezone.utc)
    assert end == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_next_month():
    start, end = extract_date_range("what's due next month", now=_NOW)

    assert start == datetime(2024, 7, 1, tzinfo=timezone.utc)
    assert end == datetime(2024, 8, 1, tzinfo=timezone.utc)


def test_next_month_handles_year_rollover():
    now = datetime(2024, 12, 15, tzinfo=timezone.utc)

    start, end = extract_date_range("next month", now=now)

    assert start == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2025, 2, 1, tzinfo=timezone.utc)


def test_this_year():
    start, end = extract_date_range("summary of this year", now=_NOW)

    assert start == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_last_year():
    start, end = extract_date_range("what happened last year", now=_NOW)

    assert start == datetime(2023, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_next_year():
    start, end = extract_date_range("plans for next year", now=_NOW)

    assert start == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_last_n_days_includes_today():
    start, end = extract_date_range("emails from the last 3 days", now=_NOW)

    assert start == datetime(2024, 6, 10, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 13, tzinfo=timezone.utc)
    assert (end - start).days == 3


def test_next_n_days_starts_today():
    start, end = extract_date_range("what's happening in the next 3 days", now=_NOW)

    assert start == datetime(2024, 6, 12, tzinfo=timezone.utc)  # today
    assert end == datetime(2024, 6, 15, tzinfo=timezone.utc)
    assert (end - start).days == 3


def test_bare_weekday_is_most_recent_occurrence_including_today():
    # _NOW is a wednesday
    start, end = extract_date_range("meeting on wednesday", now=_NOW)

    assert start == datetime(2024, 6, 12, tzinfo=timezone.utc)  # today
    assert end == datetime(2024, 6, 13, tzinfo=timezone.utc)


def test_bare_weekday_before_today_in_same_week():
    start, end = extract_date_range("meeting on monday", now=_NOW)

    assert start == datetime(2024, 6, 10, tzinfo=timezone.utc)


def test_next_weekday_when_today_is_a_different_day():
    # _NOW is wednesday; "next monday" should be the monday after this week
    start, end = extract_date_range("meeting next monday", now=_NOW)

    assert start == datetime(2024, 6, 17, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 18, tzinfo=timezone.utc)


def test_next_weekday_when_today_is_that_weekday_means_a_week_from_now():
    # _NOW is wednesday - "next wednesday" said on a wednesday should mean
    # a week from today, not today itself
    start, end = extract_date_range("meeting next wednesday", now=_NOW)

    assert start == datetime(2024, 6, 19, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 20, tzinfo=timezone.utc)


def test_upcoming_defaults_to_a_30_day_forward_window():
    start, end = extract_date_range("what's upcoming", now=_NOW)

    assert start == datetime(2024, 6, 12, tzinfo=timezone.utc)  # today
    assert end == datetime(2024, 7, 12, tzinfo=timezone.utc)


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


def test_parse_stored_date_full_datetime_with_offset():
    parsed = parse_stored_date("2024-06-01T10:00:00-05:00")

    assert parsed is not None
    assert parsed.year == 2024 and parsed.month == 6 and parsed.day == 1


def test_parse_stored_date_bare_date():
    parsed = parse_stored_date("2024-06-01")

    assert parsed == datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_parse_stored_date_naive_datetime_assumed_utc():
    parsed = parse_stored_date("2024-06-01T10:00:00")

    assert parsed == datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)


def test_parse_stored_date_none_or_empty_returns_none():
    assert parse_stored_date(None) is None
    assert parse_stored_date("") is None


def test_parse_stored_date_unparseable_returns_none():
    assert parse_stored_date("not a date") is None


def test_chunk_in_range_no_filter_always_passes():
    assert chunk_in_range("gmail", {"sent_at": "2020-01-01T00:00:00Z"}, None) is True


def test_chunk_in_range_gmail_within_range():
    date_range = (datetime(2024, 6, 10, tzinfo=timezone.utc), datetime(2024, 6, 17, tzinfo=timezone.utc))

    assert chunk_in_range("gmail", {"sent_at": "2024-06-12T09:00:00Z"}, date_range) is True


def test_chunk_in_range_gmail_outside_range():
    date_range = (datetime(2024, 6, 10, tzinfo=timezone.utc), datetime(2024, 6, 17, tzinfo=timezone.utc))

    assert chunk_in_range("gmail", {"sent_at": "2024-05-01T09:00:00Z"}, date_range) is False


def test_chunk_in_range_calendar_all_day_event():
    date_range = (datetime(2024, 6, 10, tzinfo=timezone.utc), datetime(2024, 6, 17, tzinfo=timezone.utc))

    assert chunk_in_range("calendar", {"start_at": "2024-06-12"}, date_range) is True


def test_chunk_in_range_docs_always_passes_no_date_concept():
    date_range = (datetime(2024, 6, 10, tzinfo=timezone.utc), datetime(2024, 6, 17, tzinfo=timezone.utc))

    assert chunk_in_range("docs", {"title": "My Doc"}, date_range) is True


def test_chunk_in_range_local_files_always_passes_no_date_concept():
    date_range = (datetime(2024, 6, 10, tzinfo=timezone.utc), datetime(2024, 6, 17, tzinfo=timezone.utc))

    assert chunk_in_range("local_files", {"path": "note.txt"}, date_range) is True


def test_chunk_in_range_missing_or_unparseable_date_passes():
    date_range = (datetime(2024, 6, 10, tzinfo=timezone.utc), datetime(2024, 6, 17, tzinfo=timezone.utc))

    assert chunk_in_range("gmail", {"sent_at": ""}, date_range) is True
    assert chunk_in_range("calendar", {"start_at": None}, date_range) is True
    assert chunk_in_range("gmail", {}, date_range) is True
