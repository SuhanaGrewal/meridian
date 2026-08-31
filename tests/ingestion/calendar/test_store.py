from meridian.ingestion.calendar.store import CalendarStore


def test_store_creates_events_and_sync_state_tables(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")

    tables = {
        row["name"]
        for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    assert "events" in tables
    assert "sync_state" in tables
