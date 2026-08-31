from meridian.ingestion.calendar.event_parser import ParsedEvent
from meridian.ingestion.calendar.store import CalendarStore


def _event(event_id="evt-1", calendar_id="primary", summary="Standup") -> ParsedEvent:
    return ParsedEvent(
        calendar_id=calendar_id,
        event_id=event_id,
        ical_uid=f"{event_id}@google.com",
        recurring_event_id=None,
        summary=summary,
        description="",
        location="",
        status="confirmed",
        start_at="2024-06-01T10:00:00-05:00",
        end_at="2024-06-01T10:30:00-05:00",
        is_all_day=False,
        organizer_email="alice@example.com",
        attendees=[{"email": "bob@example.com", "display_name": None, "response_status": "accepted"}],
        source_updated_at="2024-05-01T00:00:00.000Z",
    )


def test_store_creates_events_and_sync_state_tables(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")

    tables = {
        row["name"]
        for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    assert "events" in tables
    assert "sync_state" in tables


def test_upsert_event_then_read_back(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")

    store.upsert_event(_event())

    row = store.get_event_row("primary", "evt-1")
    assert row["summary"] == "Standup"
    assert row["organizer_email"] == "alice@example.com"
    assert row["attendees"] == '[{"email": "bob@example.com", "display_name": null, "response_status": "accepted"}]'
    assert store.count_events() == 1
    assert store.count_events("primary") == 1
    assert store.count_events("other-calendar") == 0


def test_upsert_event_twice_with_identical_data_results_in_one_row(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    event = _event()

    store.upsert_event(event)
    store.upsert_event(event)

    assert store.count_events() == 1


def test_upsert_event_preserves_fetched_at_but_bumps_updated_at_on_change(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    store.upsert_event(_event(summary="Standup"))
    first_row = store.get_event_row("primary", "evt-1")

    store.upsert_event(_event(summary="Standup (moved)"))
    second_row = store.get_event_row("primary", "evt-1")

    assert second_row["fetched_at"] == first_row["fetched_at"]
    assert second_row["updated_at"] >= first_row["updated_at"]
    assert second_row["summary"] == "Standup (moved)"


def test_same_event_id_on_different_calendars_are_distinct_rows(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")

    store.upsert_event(_event(event_id="evt-1", calendar_id="primary"))
    store.upsert_event(_event(event_id="evt-1", calendar_id="shared-calendar"))

    assert store.count_events() == 2
