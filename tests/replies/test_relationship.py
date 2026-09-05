from meridian.ingestion.gmail.message_parser import ParsedMessage
from meridian.ingestion.gmail.store import GmailStore
from meridian.replies.relationship import classify_relationship


def _message(message_id, sender, recipients=None, sent_at="2024-06-01T00:00:00+00:00") -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id, thread_id=f"t-{message_id}", subject="Subject", sender=sender,
        recipients=recipients or [], sent_at=sent_at, body_text="hello", label_ids=["INBOX"],
        content_hash=f"hash-{message_id}",
    )


def test_new_contact_with_no_prior_messages(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", "Alice <alice@example.com>"))

    relationship = classify_relationship(store, "alice@example.com", exclude_message_id="m1")

    assert relationship == "new"


def test_occasional_contact_with_a_few_prior_messages(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", "Alice <alice@example.com>"))
    store.upsert_message(_message("m2", "me@example.com", recipients=["alice@example.com"]))
    store.upsert_message(_message("m3", "Alice <alice@example.com>"))

    relationship = classify_relationship(store, "alice@example.com", exclude_message_id="m3")

    assert relationship == "occasional"


def test_frequent_contact_with_many_prior_messages(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    for i in range(5):
        store.upsert_message(_message(f"m{i}", "Alice <alice@example.com>"))
    store.upsert_message(_message("m-current", "Alice <alice@example.com>"))

    relationship = classify_relationship(store, "alice@example.com", exclude_message_id="m-current")

    assert relationship == "frequent"


def test_counts_messages_where_contact_is_a_recipient_too(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", "me@example.com", recipients=["alice@example.com"]))
    store.upsert_message(_message("m2", "Alice <alice@example.com>"))

    relationship = classify_relationship(store, "alice@example.com", exclude_message_id="m2")

    assert relationship == "occasional"


def test_case_insensitive_email_matching(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", "Alice <ALICE@Example.com>"))
    store.upsert_message(_message("m2", "Alice <alice@example.com>"))

    relationship = classify_relationship(store, "alice@example.com", exclude_message_id="m2")

    assert relationship == "occasional"


def test_empty_contact_email_returns_new(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")

    assert classify_relationship(store, "") == "new"
