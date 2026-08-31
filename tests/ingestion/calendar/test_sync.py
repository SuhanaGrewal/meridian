from meridian.ingestion.calendar.event_parser import parse_event
from meridian.ingestion.calendar.store import CalendarStore
from meridian.ingestion.calendar.sync import SyncStats, _store_item


def _raw_event(event_id: str, **overrides) -> dict:
    raw = {
        "id": event_id,
        "status": "confirmed",
        "summary": f"Event {event_id}",
        "start": {"dateTime": "2024-06-01T10:00:00-05:00"},
        "end": {"dateTime": "2024-06-01T10:30:00-05:00"},
    }
    raw.update(overrides)
    return raw


def test_store_item_upserts_a_confirmed_event(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    stats = SyncStats(sync_type="full")

    _store_item(store, "primary", _raw_event("evt-1"), stats)

    assert stats.events_fetched == 1
    assert store.count_events() == 1


def test_store_item_marks_cancelled_event_as_deleted(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    stats = SyncStats(sync_type="incremental")
    store.upsert_event(parse_event(_raw_event("evt-1"), calendar_id="primary"))

    _store_item(store, "primary", {"id": "evt-1", "status": "cancelled"}, stats)

    assert stats.events_deleted == 1
    assert store.get_event_row("primary", "evt-1")["is_deleted"] == 1


def test_store_item_dead_letters_malformed_event_without_id(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    stats = SyncStats(sync_type="full")

    _store_item(store, "primary", {"summary": "no id"}, stats)

    assert stats.parse_failures == 1
    assert store.count_events() == 0
