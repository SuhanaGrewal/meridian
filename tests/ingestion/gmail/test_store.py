from meridian.ingestion.gmail.message_parser import ParsedMessage
from meridian.ingestion.gmail.store import GmailStore


def _message(message_id="msg-1", label_ids=None, body_text="hello") -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id,
        thread_id="thread-1",
        subject="Subject",
        sender="alice@example.com",
        recipients=["bob@example.com"],
        sent_at="2024-01-01T00:00:00+00:00",
        body_text=body_text,
        label_ids=label_ids or ["INBOX"],
        content_hash="hash-1",
    )


def test_upsert_twice_with_identical_data_results_in_one_row(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    message = _message()

    store.upsert_message(message)
    store.upsert_message(message)

    assert store.count_messages() == 1


def test_upsert_preserves_fetched_at_but_bumps_updated_at_on_label_change(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message(label_ids=["INBOX"]))
    first_row = store.get_message_row("msg-1")

    store.upsert_message(_message(label_ids=["INBOX", "IMPORTANT"]))
    second_row = store.get_message_row("msg-1")

    assert second_row["fetched_at"] == first_row["fetched_at"]
    assert second_row["updated_at"] >= first_row["updated_at"]
    assert second_row["label_ids"] == '["INBOX", "IMPORTANT"]'


def test_update_labels_updates_without_touching_body(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message())

    store.update_labels("msg-1", ["INBOX", "STARRED"])

    row = store.get_message_row("msg-1")
    assert row["label_ids"] == '["INBOX", "STARRED"]'
    assert row["body_text"] == "hello"


def test_mark_deleted_sets_tombstone_flag(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.upsert_message(_message())

    store.mark_deleted("msg-1")

    row = store.get_message_row("msg-1")
    assert row["is_deleted"] == 1


def test_record_dead_letter_does_not_touch_messages_table(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")

    store.record_dead_letter("msg-broken", "boom")

    assert store.count_messages() == 0
    dead_letters = store._conn.execute("SELECT message_id, error FROM dead_letters").fetchall()
    assert len(dead_letters) == 1
    assert dead_letters[0]["message_id"] == "msg-broken"
    assert dead_letters[0]["error"] == "boom"


def test_sync_state_round_trip(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")

    assert store.get_sync_state().last_history_id is None

    store.set_sync_state("12345")
    state = store.get_sync_state()

    assert state.last_history_id == "12345"
    assert state.last_synced_at is not None


def test_set_sync_state_overwrites_previous_value(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")

    store.set_sync_state("111")
    store.set_sync_state("222")

    assert store.get_sync_state().last_history_id == "222"


def test_clear_sync_state_resets_to_none(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.set_sync_state("111")

    store.clear_sync_state()

    assert store.get_sync_state().last_history_id is None
