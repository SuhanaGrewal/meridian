from meridian.ingestion.local_files.note_parser import ParsedNote
from meridian.ingestion.local_files.store import NotesStore


def _note(path="note.txt", content_text="hello", size_bytes=5, mtime_ns=100) -> ParsedNote:
    return ParsedNote(
        path=path,
        content_text=content_text,
        content_hash="hash-1",
        size_bytes=size_bytes,
        mtime_ns=mtime_ns,
    )


def test_store_creates_notes_and_dead_letters_tables(tmp_path):
    store = NotesStore(tmp_path / "local_files.db")

    tables = {
        row["name"]
        for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    assert "notes" in tables
    assert "dead_letters" in tables


def test_upsert_note_then_read_back(tmp_path):
    store = NotesStore(tmp_path / "local_files.db")

    store.upsert_note(_note())

    row = store._conn.execute("SELECT * FROM notes WHERE path = ?", ("note.txt",)).fetchone()
    assert row["content_text"] == "hello"
    assert row["content_hash"] == "hash-1"
    assert row["size_bytes"] == 5
    assert row["mtime_ns"] == 100
    assert row["is_deleted"] == 0


def test_upsert_note_twice_with_identical_data_results_in_one_row(tmp_path):
    store = NotesStore(tmp_path / "local_files.db")
    note = _note()

    store.upsert_note(note)
    store.upsert_note(note)

    count = store._conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    assert count == 1


def test_upsert_note_preserves_fetched_at_but_bumps_updated_at_on_change(tmp_path):
    store = NotesStore(tmp_path / "local_files.db")
    store.upsert_note(_note(content_text="v1"))
    first_row = store._conn.execute("SELECT * FROM notes WHERE path = ?", ("note.txt",)).fetchone()

    store.upsert_note(_note(content_text="v2"))
    second_row = store._conn.execute("SELECT * FROM notes WHERE path = ?", ("note.txt",)).fetchone()

    assert second_row["fetched_at"] == first_row["fetched_at"]
    assert second_row["updated_at"] >= first_row["updated_at"]
    assert second_row["content_text"] == "v2"


def test_get_note_metadata_returns_size_and_mtime(tmp_path):
    store = NotesStore(tmp_path / "local_files.db")
    store.upsert_note(_note(size_bytes=42, mtime_ns=999))

    assert store.get_note_metadata("note.txt") == (42, 999)


def test_get_note_metadata_returns_none_for_unknown_path(tmp_path):
    store = NotesStore(tmp_path / "local_files.db")

    assert store.get_note_metadata("unknown.txt") is None
