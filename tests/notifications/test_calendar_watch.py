from datetime import datetime, timezone

from meridian.notifications.calendar_watch import check_upcoming_events
from meridian.notifications.store import NotificationStore

_NOW = datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc)


class _FakeCalendarStore:
    def __init__(self, events):
        self._events = events

    def list_events_upcoming(self, min_start_at, max_start_at):
        return self._events


def _event(calendar_id="primary", event_id="evt-1", summary="Standup", start_at="2024-06-03T09:10:00+00:00", is_all_day=0):
    return {"calendar_id": calendar_id, "event_id": event_id, "summary": summary, "start_at": start_at, "is_all_day": is_all_day}


def test_check_upcoming_events_returns_and_marks_new_event(tmp_path):
    notification_store = NotificationStore(tmp_path / "notifications.db")
    calendar_store = _FakeCalendarStore([_event()])

    events = check_upcoming_events(calendar_store, notification_store, now=_NOW)

    assert len(events) == 1
    assert events[0].event_id == "primary:evt-1"
    assert events[0].summary == "Standup"
    assert notification_store.has_notified("primary:evt-1") is True


def test_check_upcoming_events_does_not_renotify_same_event(tmp_path):
    notification_store = NotificationStore(tmp_path / "notifications.db")
    calendar_store = _FakeCalendarStore([_event()])

    first = check_upcoming_events(calendar_store, notification_store, now=_NOW)
    second = check_upcoming_events(calendar_store, notification_store, now=_NOW)

    assert len(first) == 1
    assert len(second) == 0


def test_check_upcoming_events_excludes_all_day_events(tmp_path):
    notification_store = NotificationStore(tmp_path / "notifications.db")
    calendar_store = _FakeCalendarStore([_event(is_all_day=1)])

    events = check_upcoming_events(calendar_store, notification_store, now=_NOW)

    assert events == []


def test_check_upcoming_events_with_no_events_returns_empty(tmp_path):
    notification_store = NotificationStore(tmp_path / "notifications.db")
    calendar_store = _FakeCalendarStore([])

    events = check_upcoming_events(calendar_store, notification_store, now=_NOW)

    assert events == []


def test_check_upcoming_events_two_distinct_events_both_returned(tmp_path):
    notification_store = NotificationStore(tmp_path / "notifications.db")
    calendar_store = _FakeCalendarStore([
        _event(event_id="evt-1", summary="Standup"),
        _event(event_id="evt-2", summary="1:1 with Nick"),
    ])

    events = check_upcoming_events(calendar_store, notification_store, now=_NOW)

    assert {event.summary for event in events} == {"Standup", "1:1 with Nick"}
