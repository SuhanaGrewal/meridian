from meridian.indexing.source_readers import read_gmail_items
from meridian.ingestion.gmail.message_parser import ParsedMessage
from meridian.ingestion.gmail.store import GmailStore


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
