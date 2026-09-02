from meridian.ingestion.local_files.note_parser import ParsedNote


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
