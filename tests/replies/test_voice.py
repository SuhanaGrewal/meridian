from meridian.ingestion.gmail.message_parser import ParsedMessage
from meridian.ingestion.gmail.store import GmailStore
from meridian.replies.voice import sample_voice_examples

_ACCOUNT_EMAIL = "me@example.com"


def _message(message_id, sender, body_text, sent_at="2024-06-01T00:00:00+00:00") -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id, thread_id=f"t-{message_id}", subject="Subject", sender=sender,
        recipients=[], sent_at=sent_at, body_text=body_text, label_ids=["INBOX"],
        content_hash=f"hash-{message_id}",
    )


def test_sample_voice_examples_only_includes_sent_messages(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", _ACCOUNT_EMAIL, "This is a real substantive reply about the project."))
    store.upsert_message(_message("m2", "alice@example.com", "This is Alice's message, not mine at all here."))

    examples = sample_voice_examples(store, _ACCOUNT_EMAIL)

    assert len(examples) == 1
    assert "real substantive reply" in examples[0]


def test_sample_voice_examples_skips_trivially_short_messages(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", _ACCOUNT_EMAIL, "Thanks!"))

    examples = sample_voice_examples(store, _ACCOUNT_EMAIL)

    assert examples == []


def test_sample_voice_examples_orders_most_recent_first(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", _ACCOUNT_EMAIL, "This is the older substantive message here.", sent_at="2024-01-01T00:00:00+00:00"))
    store.upsert_message(_message("m2", _ACCOUNT_EMAIL, "This is the newer substantive message here.", sent_at="2024-06-01T00:00:00+00:00"))

    examples = sample_voice_examples(store, _ACCOUNT_EMAIL)

    assert "newer" in examples[0]
    assert "older" in examples[1]


def test_sample_voice_examples_respects_limit(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    for i in range(7):
        store.upsert_message(_message(f"m{i}", _ACCOUNT_EMAIL, f"This is substantive sent message number {i} here."))

    examples = sample_voice_examples(store, _ACCOUNT_EMAIL, limit=3)

    assert len(examples) == 3


def test_sample_voice_examples_with_no_sent_mail_returns_empty(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", "alice@example.com", "A substantive message from someone else entirely."))

    assert sample_voice_examples(store, _ACCOUNT_EMAIL) == []
