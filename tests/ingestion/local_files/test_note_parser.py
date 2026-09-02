from pathlib import Path

from meridian.ingestion.local_files.note_parser import ParsedNote, _read_file_bytes


def test_parsed_note_holds_expected_fields():
    note = ParsedNote(
        path="sub/note.txt",
        content_text="hello",
        content_hash="hash-1",
        size_bytes=5,
        mtime_ns=123,
    )

    assert note.path == "sub/note.txt"
    assert note.content_text == "hello"
    assert note.content_hash == "hash-1"
    assert note.size_bytes == 5
    assert note.mtime_ns == 123


def test_read_file_bytes_reads_real_file(tmp_path):
    path = tmp_path / "note.txt"
    path.write_bytes(b"hello world")

    assert _read_file_bytes(path) == b"hello world"


def test_read_file_bytes_retries_transient_oserror_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: None)
    path = tmp_path / "note.txt"
    path.write_bytes(b"hello world")

    calls = {"count": 0}
    real_read_bytes = Path.read_bytes

    def flaky_read_bytes(self):
        calls["count"] += 1
        if calls["count"] < 2:
            raise OSError("file temporarily locked")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", flaky_read_bytes)

    assert _read_file_bytes(path) == b"hello world"
    assert calls["count"] == 2
