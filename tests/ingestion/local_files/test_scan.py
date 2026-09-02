from meridian.ingestion.local_files.scan import DEFAULT_EXTENSIONS, ScanStats


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
