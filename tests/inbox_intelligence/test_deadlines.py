from datetime import date

from meridian.inbox_intelligence.deadlines import resolve_deadline_phrase

# 2026-09-02 is a Wednesday
_ANCHOR = date(2026, 9, 2)


def test_none_or_empty_phrase_returns_none():
    assert resolve_deadline_phrase(None, _ANCHOR) is None
    assert resolve_deadline_phrase("", _ANCHOR) is None
    assert resolve_deadline_phrase("NONE", _ANCHOR) is None


def test_today_variants():
    assert resolve_deadline_phrase("today", _ANCHOR) == _ANCHOR
    assert resolve_deadline_phrase("end of day", _ANCHOR) == _ANCHOR
    assert resolve_deadline_phrase("EOD", _ANCHOR) == _ANCHOR


def test_tomorrow():
    assert resolve_deadline_phrase("tomorrow", _ANCHOR) == date(2026, 9, 3)


def test_end_of_week_resolves_to_friday_same_week():
    assert resolve_deadline_phrase("end of week", _ANCHOR) == date(2026, 9, 4)


def test_next_week_is_seven_days_out():
    assert resolve_deadline_phrase("next week", _ANCHOR) == date(2026, 9, 9)


def test_in_n_days():
    assert resolve_deadline_phrase("in 3 days", _ANCHOR) == date(2026, 9, 5)
    assert resolve_deadline_phrase("in 1 day", _ANCHOR) == date(2026, 9, 3)


def test_bare_weekday_resolves_to_next_occurrence():
    # anchor is wednesday - "friday" should be the same week
    assert resolve_deadline_phrase("Friday", _ANCHOR) == date(2026, 9, 4)
    # "monday" should be the following week, since monday already passed this week
    assert resolve_deadline_phrase("Monday", _ANCHOR) == date(2026, 9, 7)


def test_by_prefix_is_stripped():
    assert resolve_deadline_phrase("by Friday", _ANCHOR) == date(2026, 9, 4)
    assert resolve_deadline_phrase("before Friday", _ANCHOR) == date(2026, 9, 4)


def test_weekday_same_as_anchor_resolves_to_anchor_itself():
    # anchor is wednesday
    assert resolve_deadline_phrase("Wednesday", _ANCHOR) == _ANCHOR


def test_unrecognized_phrase_returns_none_rather_than_guessing():
    assert resolve_deadline_phrase("sometime next quarter", _ANCHOR) is None
