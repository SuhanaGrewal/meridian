from datetime import datetime, timezone

from meridian.inbox_intelligence.stale_threads import find_stale_threads
from meridian.ingestion.gmail.message_parser import ParsedMessage
from meridian.ingestion.gmail.store import GmailStore

_NOW = datetime(2024, 6, 10, tzinfo=timezone.utc)
_ACCOUNT_EMAIL = "me@example.com"


def _message(message_id, thread_id, sender, sent_at, body_text="hello") -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id,
        thread_id=thread_id,
        subject=f"Subject {thread_id}",
        sender=sender,
        recipients=["someone@example.com"],
        sent_at=sent_at,
        body_text=body_text,
        label_ids=["INBOX"],
        content_hash=f"hash-{message_id}",
    )


def test_thread_waiting_on_reply_is_flagged_stale(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-05T00:00:00+00:00"))

    threads = find_stale_threads(store, _ACCOUNT_EMAIL, now=_NOW, min_days_quiet=3)

    assert len(threads) == 1
    assert threads[0].thread_id == "t1"
    assert threads[0].days_quiet == 5


def test_thread_last_replied_by_account_owner_is_not_stale(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-01T00:00:00+00:00"))
    store.upsert_message(_message("m2", "t1", "Me <me@example.com>", "2024-06-05T00:00:00+00:00"))

    threads = find_stale_threads(store, _ACCOUNT_EMAIL, now=_NOW, min_days_quiet=3)

    assert threads == []


def test_thread_too_recent_is_not_yet_stale(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-09T00:00:00+00:00"))

    threads = find_stale_threads(store, _ACCOUNT_EMAIL, now=_NOW, min_days_quiet=3)

    assert threads == []


def test_account_email_match_is_case_insensitive(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", "t1", "Me <ME@EXAMPLE.COM>", "2024-06-05T00:00:00+00:00"))

    threads = find_stale_threads(store, _ACCOUNT_EMAIL, now=_NOW, min_days_quiet=3)

    assert threads == []


def test_multiple_stale_threads_sorted_by_days_quiet_descending(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-07T00:00:00+00:00"))
    store.upsert_message(_message("m2", "t2", "Bob <bob@example.com>", "2024-06-01T00:00:00+00:00"))

    threads = find_stale_threads(store, _ACCOUNT_EMAIL, now=_NOW, min_days_quiet=3)

    assert [thread.thread_id for thread in threads] == ["t2", "t1"]


def test_snippet_is_truncated_to_200_chars(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(
        _message("m1", "t1", "Alice <alice@example.com>", "2024-06-01T00:00:00+00:00", body_text="x" * 500)
    )

    threads = find_stale_threads(store, _ACCOUNT_EMAIL, now=_NOW, min_days_quiet=3)

    assert len(threads[0].last_message_snippet) == 200
