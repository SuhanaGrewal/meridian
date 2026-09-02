from meridian.ingestion.local_files.scan import DEFAULT_EXTENSIONS, ScanStats, _iter_note_files


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
