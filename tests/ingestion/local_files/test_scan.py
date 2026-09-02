from meridian.ingestion.local_files.scan import (
    DEFAULT_EXTENSIONS,
    ScanStats,
    _iter_note_files,
    _scan_one_file,
    run_scan,
)
from meridian.ingestion.local_files.store import NotesStore


def test_scan_stats_defaults_to_zero():
    stats = ScanStats()

    assert stats.files_scanned == 0
    assert stats.notes_added == 0
    assert stats.notes_updated == 0
    assert stats.notes_skipped_unchanged == 0
    assert stats.notes_deleted == 0
    assert stats.parse_failures == 0
    assert stats.duration_ms == 0.0


def test_default_extensions_includes_txt_and_md():
    assert DEFAULT_EXTENSIONS == {".txt", ".md"}


def test_iter_note_files_includes_matching_extensions(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.md").write_text("b")
    (tmp_path / "c.png").write_bytes(b"not text")

    found = {p.name for p in _iter_note_files(tmp_path, DEFAULT_EXTENSIONS)}

    assert found == {"a.txt", "b.md"}


def test_iter_note_files_recurses_into_subfolders(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.txt").write_text("nested")

    found = list(_iter_note_files(tmp_path, DEFAULT_EXTENSIONS))

    assert len(found) == 1
    assert found[0].name == "nested.txt"


def test_iter_note_files_skips_dotfiles_and_dot_directories(tmp_path):
    (tmp_path / ".hidden.txt").write_text("hidden")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "note.txt").write_text("inside git dir")
    (tmp_path / "visible.txt").write_text("visible")

    found = {p.name for p in _iter_note_files(tmp_path, DEFAULT_EXTENSIONS)}

    assert found == {"visible.txt"}


def test_iter_note_files_returns_sorted_results(tmp_path):
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "a.txt").write_text("a")

    found = [p.name for p in _iter_note_files(tmp_path, DEFAULT_EXTENSIONS)]

    assert found == ["a.txt", "b.txt"]


def _setup(tmp_path):
    notes_folder = tmp_path / "notes"
    notes_folder.mkdir()
    db_path = tmp_path / "local_files.db"
    return notes_folder, NotesStore(db_path)


def test_scan_one_file_adds_new_file(tmp_path):
    notes_folder, store = _setup(tmp_path)
    file_path = notes_folder / "note.txt"
    file_path.write_text("hello")
    stats = ScanStats()

    _scan_one_file(file_path, notes_folder=notes_folder, store=store, stats=stats)

    assert stats.notes_added == 1
    assert stats.files_scanned == 1
    assert store.count_notes() == 1


def test_scan_one_file_skips_unchanged_file_without_rereading(tmp_path):
    notes_folder, store = _setup(tmp_path)
    file_path = notes_folder / "note.txt"
    file_path.write_text("hello")
    stats = ScanStats()
    _scan_one_file(file_path, notes_folder=notes_folder, store=store, stats=stats)
    first_row = store.get_note_row("note.txt")

    second_stats = ScanStats()
    _scan_one_file(file_path, notes_folder=notes_folder, store=store, stats=second_stats)
    second_row = store.get_note_row("note.txt")

    assert second_stats.notes_skipped_unchanged == 1
    assert second_stats.notes_added == 0
    assert second_row["updated_at"] == first_row["updated_at"]


def test_scan_one_file_updates_changed_file(tmp_path):
    notes_folder, store = _setup(tmp_path)
    file_path = notes_folder / "note.txt"
    file_path.write_text("v1")
    _scan_one_file(file_path, notes_folder=notes_folder, store=store, stats=ScanStats())

    file_path.write_text("v2 - longer content")
    stats = ScanStats()
    _scan_one_file(file_path, notes_folder=notes_folder, store=store, stats=stats)

    assert stats.notes_updated == 1
    assert store.get_note_row("note.txt")["content_text"] == "v2 - longer content"


def test_scan_one_file_force_rehash_rereads_unchanged_file(tmp_path):
    notes_folder, store = _setup(tmp_path)
    file_path = notes_folder / "note.txt"
    file_path.write_text("hello")
    _scan_one_file(file_path, notes_folder=notes_folder, store=store, stats=ScanStats())

    stats = ScanStats()
    _scan_one_file(
        file_path, notes_folder=notes_folder, store=store, stats=stats, force_rehash=True
    )

    assert stats.notes_skipped_unchanged == 0
    assert stats.notes_updated == 1


def test_scan_one_file_dead_letters_invalid_utf8_without_raising(tmp_path):
    notes_folder, store = _setup(tmp_path)
    file_path = notes_folder / "note.txt"
    file_path.write_bytes(b"\xff\xfe not valid utf-8")
    stats = ScanStats()

    _scan_one_file(file_path, notes_folder=notes_folder, store=store, stats=stats)

    assert stats.parse_failures == 1
    assert store.count_notes() == 0
    dead_letters = store._conn.execute("SELECT path FROM dead_letters").fetchall()
    assert len(dead_letters) == 1


def test_run_scan_with_none_folder_returns_empty_stats(tmp_path):
    _, store = _setup(tmp_path)

    stats = run_scan(None, store)

    assert stats == ScanStats()


def test_run_scan_with_nonexistent_folder_returns_empty_stats(tmp_path):
    _, store = _setup(tmp_path)

    stats = run_scan(tmp_path / "does-not-exist", store)

    assert stats == ScanStats()


def test_run_scan_ingests_all_matching_files(tmp_path):
    notes_folder, store = _setup(tmp_path)
    (notes_folder / "a.txt").write_text("a")
    (notes_folder / "b.md").write_text("b")
    (notes_folder / "c.png").write_bytes(b"skip me")

    stats = run_scan(notes_folder, store)

    assert stats.notes_added == 2
    assert stats.files_scanned == 2
    assert store.count_notes() == 2


def test_run_scan_is_idempotent_when_rerun_unchanged(tmp_path):
    notes_folder, store = _setup(tmp_path)
    (notes_folder / "a.txt").write_text("a")

    run_scan(notes_folder, store)
    stats = run_scan(notes_folder, store)

    assert stats.notes_skipped_unchanged == 1
    assert stats.notes_added == 0
    assert store.count_notes() == 1


def test_run_scan_tombstones_file_deleted_from_disk(tmp_path):
    notes_folder, store = _setup(tmp_path)
    file_path = notes_folder / "a.txt"
    file_path.write_text("a")
    run_scan(notes_folder, store)

    file_path.unlink()
    stats = run_scan(notes_folder, store)

    assert stats.notes_deleted == 1
    assert store.get_note_row("a.txt")["is_deleted"] == 1
