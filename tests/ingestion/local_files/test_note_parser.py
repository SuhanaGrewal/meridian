import hashlib
from pathlib import Path

import pytest

from meridian.ingestion.local_files.note_parser import (
    NoteParseError,
    ParsedNote,
    _read_file_bytes,
    parse_note_file,
)


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


def test_parse_note_file_extracts_content_and_metadata(tmp_path):
    notes_folder = tmp_path / "notes"
    (notes_folder / "sub").mkdir(parents=True)
    file_path = notes_folder / "sub" / "note.txt"
    file_path.write_text("hello world", encoding="utf-8")

    parsed = parse_note_file(file_path, relative_to=notes_folder)

    assert parsed.path == "sub/note.txt"
    assert parsed.content_text == "hello world"
    assert parsed.content_hash == hashlib.sha256(b"hello world").hexdigest()
    assert parsed.size_bytes == len(b"hello world")
    assert parsed.mtime_ns > 0


def test_parse_note_file_invalid_utf8_raises_note_parse_error(tmp_path):
    notes_folder = tmp_path / "notes"
    notes_folder.mkdir()
    file_path = notes_folder / "bad.txt"
    file_path.write_bytes(b"\xff\xfe not valid utf-8")

    with pytest.raises(NoteParseError):
        parse_note_file(file_path, relative_to=notes_folder)
