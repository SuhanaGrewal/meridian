from meridian.indexing.source_readers import (
    read_calendar_items,
    read_docs_items,
    read_gmail_items,
    read_local_files_items,
)
from meridian.ingestion.calendar.event_parser import ParsedEvent
from meridian.ingestion.calendar.store import CalendarStore
from meridian.ingestion.docs.doc_parser import ParsedDoc
from meridian.ingestion.docs.store import DocsStore
from meridian.ingestion.gmail.message_parser import ParsedMessage
from meridian.ingestion.gmail.store import GmailStore
from meridian.ingestion.local_files.note_parser import ParsedNote
from meridian.ingestion.local_files.store import NotesStore


def _note(path="note.txt", content_text="Some note content.") -> ParsedNote:
    return ParsedNote(
        path=path,
        content_text=content_text,
        content_hash="hash-1",
        size_bytes=len(content_text),
        mtime_ns=100,
    )


def _doc(doc_id="doc-1", title="My Doc", content_text="## Section\nBody text.") -> ParsedDoc:
    return ParsedDoc(
        doc_id=doc_id,
        title=title,
        content_text=content_text,
        modified_time="2024-06-01T00:00:00.000Z",
        content_hash="hash-1",
    )


def _calendar_event(
    event_id="evt-1",
    calendar_id="primary",
    summary="Standup",
    description="Daily sync",
    location="Room 1",
) -> ParsedEvent:
    return ParsedEvent(
        calendar_id=calendar_id,
        event_id=event_id,
        ical_uid=f"{event_id}@google.com",
        recurring_event_id=None,
        summary=summary,
        description=description,
        location=location,
        status="confirmed",
        start_at="2024-06-01T10:00:00-05:00",
        end_at="2024-06-01T10:30:00-05:00",
        is_all_day=False,
        organizer_email="alice@example.com",
        attendees=[],
        source_updated_at="2024-05-01T00:00:00.000Z",
    )


def _gmail_message(message_id="msg-1", subject="Hello", body="Body text", is_deleted=False) -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id,
        thread_id="thread-1",
        subject=subject,
        sender="alice@example.com",
        recipients=["bob@example.com"],
        sent_at="2024-01-01T00:00:00+00:00",
        body_text=body,
        label_ids=["INBOX"],
        content_hash="hash-1",
    )


def test_read_gmail_items_returns_expected_fields(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_gmail_message())

    items = read_gmail_items(tmp_path / "gmail.db")

    assert len(items) == 1
    item = items[0]
    assert item.item_id == "msg-1"
    assert item.text == "Hello\n\nBody text"
    assert item.has_headings is False
    assert item.change_signal == "hash-1"
    assert item.metadata["sender"] == "alice@example.com"
    assert item.metadata["subject"] == "Hello"


def test_read_gmail_items_excludes_deleted_messages(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_gmail_message(message_id="msg-1"))
    store.upsert_message(_gmail_message(message_id="msg-2"))
    store.mark_deleted("msg-2")

    items = read_gmail_items(tmp_path / "gmail.db")

    assert {item.item_id for item in items} == {"msg-1"}


def test_read_gmail_items_handles_missing_db_file(tmp_path):
    items = read_gmail_items(tmp_path / "does-not-exist.db")

    assert items == []


def test_read_gmail_items_handles_empty_subject_and_body(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_gmail_message(subject="", body=""))

    items = read_gmail_items(tmp_path / "gmail.db")

    assert items[0].text == ""


def test_read_calendar_items_returns_expected_fields(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    store.upsert_event(_calendar_event())

    items = read_calendar_items(tmp_path / "calendar.db")

    assert len(items) == 1
    item = items[0]
    assert item.item_id == "primary:evt-1"
    assert item.text == "Standup\nDaily sync\nRoom 1"
    assert item.has_headings is False
    assert item.change_signal == "2024-05-01T00:00:00.000Z"
    assert item.metadata["summary"] == "Standup"
    assert item.metadata["calendar_id"] == "primary"


def test_read_calendar_items_skips_missing_fields(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    store.upsert_event(_calendar_event(description="", location=""))

    items = read_calendar_items(tmp_path / "calendar.db")

    assert items[0].text == "Standup"


def test_read_calendar_items_excludes_deleted_events(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    store.upsert_event(_calendar_event(event_id="evt-1"))
    store.upsert_event(_calendar_event(event_id="evt-2"))
    store.mark_deleted("primary", "evt-2")

    items = read_calendar_items(tmp_path / "calendar.db")

    assert {item.item_id for item in items} == {"primary:evt-1"}


def test_read_calendar_items_handles_missing_db_file(tmp_path):
    assert read_calendar_items(tmp_path / "does-not-exist.db") == []


def test_read_calendar_items_distinguishes_same_event_id_across_calendars(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    store.upsert_event(_calendar_event(event_id="evt-1", calendar_id="primary"))
    store.upsert_event(_calendar_event(event_id="evt-1", calendar_id="shared"))

    items = read_calendar_items(tmp_path / "calendar.db")

    assert {item.item_id for item in items} == {"primary:evt-1", "shared:evt-1"}


def test_read_docs_items_prepends_title_as_heading(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(_doc())

    items = read_docs_items(tmp_path / "docs.db")

    assert len(items) == 1
    item = items[0]
    assert item.item_id == "doc-1"
    assert item.text == "# My Doc\n\n## Section\nBody text."
    assert item.has_headings is True
    assert item.change_signal == "hash-1"
    assert item.metadata["title"] == "My Doc"


def test_read_docs_items_handles_missing_title(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(_doc(title=""))

    items = read_docs_items(tmp_path / "docs.db")

    assert items[0].text == "## Section\nBody text."


def test_read_docs_items_excludes_trashed_docs(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(_doc(doc_id="doc-1"))
    store.upsert_document(_doc(doc_id="doc-2"))
    store.mark_trashed("doc-2")

    items = read_docs_items(tmp_path / "docs.db")

    assert {item.item_id for item in items} == {"doc-1"}


def test_read_docs_items_handles_missing_db_file(tmp_path):
    assert read_docs_items(tmp_path / "does-not-exist.db") == []


def test_read_local_files_items_returns_expected_fields(tmp_path):
    store = NotesStore(tmp_path / "local_files.db")
    store.upsert_note(_note())

    items = read_local_files_items(tmp_path / "local_files.db")

    assert len(items) == 1
    item = items[0]
    assert item.item_id == "note.txt"
    assert item.text == "Some note content."
    assert item.has_headings is False
    assert item.change_signal == "hash-1"
    assert item.metadata["path"] == "note.txt"


def test_read_local_files_items_excludes_deleted_notes(tmp_path):
    store = NotesStore(tmp_path / "local_files.db")
    store.upsert_note(_note(path="a.txt"))
    store.upsert_note(_note(path="b.txt"))
    store.mark_deleted("b.txt")

    items = read_local_files_items(tmp_path / "local_files.db")

    assert {item.item_id for item in items} == {"a.txt"}


def test_read_local_files_items_handles_missing_db_file(tmp_path):
    assert read_local_files_items(tmp_path / "does-not-exist.db") == []
