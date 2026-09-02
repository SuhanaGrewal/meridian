from meridian.ingestion.local_files.store import NotesStore


def test_store_creates_notes_and_dead_letters_tables(tmp_path):
    store = NotesStore(tmp_path / "local_files.db")

    tables = {
        row["name"]
        for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    assert "notes" in tables
    assert "dead_letters" in tables
