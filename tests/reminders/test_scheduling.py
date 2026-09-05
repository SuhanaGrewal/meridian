from datetime import datetime, timedelta, timezone

from meridian.reminders.scheduling import propose_free_slot


class _FakeCalendarStore:
    def __init__(self, events):
        self._events = events

    def list_events_upcoming(self, min_start_at, max_start_at):
        return self._events


def _event(start_at, end_at, is_all_day=False):
    return {"start_at": start_at, "end_at": end_at, "is_all_day": is_all_day}


def test_propose_free_slot_with_no_events_returns_slot_right_now(tmp_path=None):
    now = datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc)  # Monday
    store = _FakeCalendarStore([])

    slot = propose_free_slot(store, now=now)

    assert slot == (now, now + timedelta(minutes=30))


def test_propose_free_slot_skips_past_a_busy_block(tmp_path=None):
    now = datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc)  # Monday
    store = _FakeCalendarStore([
        _event("2024-06-03T10:00:00+00:00", "2024-06-03T16:45:00+00:00"),
    ])

    slot = propose_free_slot(store, now=now)

    # only 15 minutes remain in the business day after the meeting ends -
    # not enough for a 30-minute slot, so it rolls to the next business day.
    assert slot == (
        datetime(2024, 6, 4, 9, 0, tzinfo=timezone.utc),
        datetime(2024, 6, 4, 9, 30, tzinfo=timezone.utc),
    )


def test_propose_free_slot_finds_a_gap_between_two_events(tmp_path=None):
    now = datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc)  # Monday
    store = _FakeCalendarStore([
        _event("2024-06-03T09:00:00+00:00", "2024-06-03T10:00:00+00:00"),
        _event("2024-06-03T11:00:00+00:00", "2024-06-03T17:00:00+00:00"),
    ])

    slot = propose_free_slot(store, now=now)

    # the gap between the two events (10:00-11:00) is a full hour - big
    # enough for the default 30-minute slot, unlike a too-small gap.
    assert slot == (
        datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc),
        datetime(2024, 6, 3, 10, 30, tzinfo=timezone.utc),
    )


def test_propose_free_slot_skips_weekend(tmp_path=None):
    now = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)  # Saturday
    store = _FakeCalendarStore([])

    slot = propose_free_slot(store, now=now)

    assert slot == (
        datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc),
        datetime(2024, 6, 3, 9, 30, tzinfo=timezone.utc),
    )


def test_propose_free_slot_after_hours_rolls_to_next_day(tmp_path=None):
    now = datetime(2024, 6, 3, 18, 0, tzinfo=timezone.utc)  # Monday evening
    store = _FakeCalendarStore([])

    slot = propose_free_slot(store, now=now)

    assert slot == (
        datetime(2024, 6, 4, 9, 0, tzinfo=timezone.utc),
        datetime(2024, 6, 4, 9, 30, tzinfo=timezone.utc),
    )


def test_propose_free_slot_ignores_all_day_events(tmp_path=None):
    now = datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc)  # Monday
    store = _FakeCalendarStore([
        _event("2024-06-03T00:00:00+00:00", "2024-06-04T00:00:00+00:00", is_all_day=True),
    ])

    slot = propose_free_slot(store, now=now)

    assert slot == (now, now + timedelta(minutes=30))


def test_propose_free_slot_returns_none_when_fully_booked_for_the_window(tmp_path=None):
    now = datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc)  # Monday
    events = []
    day = now
    for _ in range(8):  # every business day fully booked for a week+
        if day.weekday() < 5:
            events.append(_event(
                day.replace(hour=9, minute=0).isoformat(), day.replace(hour=17, minute=0).isoformat()
            ))
        day += timedelta(days=1)
    store = _FakeCalendarStore(events)

    slot = propose_free_slot(store, now=now, lookahead_days=7)

    assert slot is None
