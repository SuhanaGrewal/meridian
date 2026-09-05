import base64
import json

import httplib2
import pytest
from googleapiclient.errors import HttpError

from meridian.ingestion.gmail.message_parser import parse_message
from meridian.ingestion.gmail.store import GmailStore
from meridian.ingestion.gmail.sync import _full_backfill, run_sync


def _raw_message(message_id: str) -> dict:
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "labelIds": ["INBOX"],
        "internalDate": "1700000000000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": f"Subject {message_id}"},
                {"name": "From", "value": "alice@example.com"},
                {"name": "To", "value": "bob@example.com"},
            ],
            "body": {
                "data": base64.urlsafe_b64encode(f"Body {message_id}".encode("utf-8")).decode("ascii")
            },
        },
    }


def _http_error(status: int, *, retry_after: str | None = None, reason: str | None = None) -> HttpError:
    headers = {"status": str(status)}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    resp = httplib2.Response(headers)
    errors = [{"reason": reason}] if reason else []
    content = json.dumps({"error": {"errors": errors}}).encode("utf-8")
    return HttpError(resp, content)


class _Request:
    def __init__(self, result):
        self._result = result

    def execute(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _QueuedRequest:
    """Mimics retrying the *same* request object's .execute() across attempts."""

    def __init__(self, outcomes: list):
        self._outcomes = outcomes

    def execute(self):
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeMessages:
    def __init__(self, list_pages, get_responses):
        self._list_pages = list(list_pages)
        self._get_responses = {
            key: (list(value) if isinstance(value, list) else [value])
            for key, value in (get_responses or {}).items()
        }
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return _Request(self._list_pages.pop(0))

    def get(self, **kwargs):
        return _QueuedRequest(self._get_responses[kwargs["id"]])


class _FakeHistory:
    def __init__(self, pages):
        self._pages = list(pages)

    def list(self, **kwargs):
        return _Request(self._pages.pop(0))


class _FakeUsers:
    def __init__(self, profile, messages, history):
        self._profile = profile
        self._messages = messages
        self._history = history

    def getProfile(self, **kwargs):
        return _Request(self._profile)

    def messages(self):
        return self._messages

    def history(self):
        return self._history


class _FakeService:
    def __init__(self, *, profile=None, list_pages=None, get_responses=None, history_pages=None):
        self.messages_double = _FakeMessages(list_pages or [], get_responses or {})
        self.history_double = _FakeHistory(history_pages or [])
        merged_profile = {"emailAddress": "me@example.com", **(profile or {})}
        self._users = _FakeUsers(merged_profile, self.messages_double, self.history_double)

    def users(self):
        return self._users


def test_first_run_captures_history_id_before_backfill_and_persists_after(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    service = _FakeService(
        profile={"historyId": "1000"},
        list_pages=[{"messages": [{"id": "m1"}, {"id": "m2"}]}],
        get_responses={"m1": _raw_message("m1"), "m2": _raw_message("m2")},
    )

    stats = run_sync(service, store)

    assert stats.sync_type == "full"
    assert stats.messages_fetched == 2
    assert store.count_messages() == 2
    assert store.get_sync_state().last_history_id == "1000"


def test_full_backfill_paginates_across_multiple_pages(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    service = _FakeService(
        profile={"historyId": "1000"},
        list_pages=[
            {"messages": [{"id": "m1"}], "nextPageToken": "p2"},
            {"messages": [{"id": "m2"}]},
        ],
        get_responses={"m1": _raw_message("m1"), "m2": _raw_message("m2")},
    )

    stats = run_sync(service, store)

    assert stats.messages_fetched == 2
    assert store.count_messages() == 2


def test_full_backfill_passes_query_through_to_messages_list(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    service = _FakeService(profile={"historyId": "1"}, list_pages=[{"messages": []}])

    run_sync(service, store, query="newer_than:30d")

    assert service.messages_double.list_calls[0]["q"] == "newer_than:30d"


def test_full_backfill_is_idempotent_when_rerun(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    raw = _raw_message("m1")

    service_one = _FakeService(
        profile={"historyId": "1000"},
        list_pages=[{"messages": [{"id": "m1"}]}],
        get_responses={"m1": raw},
    )
    _full_backfill(service_one, store, rate_limiter=None, logger=None, query="")

    service_two = _FakeService(
        profile={"historyId": "1000"},
        list_pages=[{"messages": [{"id": "m1"}]}],
        get_responses={"m1": raw},
    )
    _full_backfill(service_two, store, rate_limiter=None, logger=None, query="")

    assert store.count_messages() == 1


def test_first_run_captures_account_email(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    service = _FakeService(
        profile={"historyId": "1000", "emailAddress": "suhana@example.com"},
        list_pages=[{"messages": []}],
    )

    run_sync(service, store)

    assert store.get_account_email() == "suhana@example.com"


def test_incremental_sync_captures_account_email_when_missing(tmp_path):
    """covers a database that was already fully backfilled before
    account_email existed - the very next sync, even an incremental one,
    must self-heal and capture it without needing a --full-resync."""
    store = GmailStore(tmp_path / "gmail.db")
    store.set_sync_state("500")
    service = _FakeService(
        profile={"emailAddress": "suhana@example.com"},
        history_pages=[{"history": [], "historyId": "500"}],
    )

    run_sync(service, store)

    assert store.get_account_email() == "suhana@example.com"


def test_incremental_sync_uses_stored_history_id(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.set_sync_state("500")

    service = _FakeService(
        history_pages=[
            {"history": [{"messagesAdded": [{"message": {"id": "m3"}}]}], "historyId": "600"}
        ],
        get_responses={"m3": _raw_message("m3")},
    )

    stats = run_sync(service, store)

    assert stats.sync_type == "incremental"
    assert stats.messages_fetched == 1
    assert store.get_sync_state().last_history_id == "600"


def test_incremental_sync_paginates_history(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.set_sync_state("500")

    service = _FakeService(
        history_pages=[
            {
                "history": [{"messagesAdded": [{"message": {"id": "m1"}}]}],
                "historyId": "600",
                "nextPageToken": "p2",
            },
            {"history": [{"messagesAdded": [{"message": {"id": "m2"}}]}], "historyId": "700"},
        ],
        get_responses={"m1": _raw_message("m1"), "m2": _raw_message("m2")},
    )

    stats = run_sync(service, store)

    assert stats.messages_fetched == 2
    assert store.get_sync_state().last_history_id == "700"


def test_incremental_sync_handles_labels_and_deletes_without_extra_fetch(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.set_sync_state("500")
    store.upsert_message(parse_message(_raw_message("m1")))

    service = _FakeService(
        history_pages=[
            {
                "history": [
                    {"labelsAdded": [{"message": {"id": "m1", "labelIds": ["INBOX", "STARRED"]}}]},
                    {"messagesDeleted": [{"message": {"id": "m1"}}]},
                ],
                "historyId": "600",
            }
        ],
    )

    stats = run_sync(service, store)

    assert stats.messages_updated == 1
    assert stats.messages_deleted == 1
    row = store.get_message_row("m1")
    assert row["is_deleted"] == 1


def test_malformed_message_is_dead_lettered_and_batch_continues(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    service = _FakeService(
        profile={"historyId": "1000"},
        list_pages=[{"messages": [{"id": "m1"}, {"id": "m2"}]}],
        get_responses={"m1": _raw_message("m1"), "m2": {"id": "m2"}},  # m2 missing threadId/payload
    )

    stats = run_sync(service, store)

    assert stats.messages_fetched == 1
    assert stats.parse_failures == 1
    assert store.count_messages() == 1


def test_rate_limited_fetch_waits_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr("meridian.common.google_api.time.sleep", lambda s: None)
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: None)

    store = GmailStore(tmp_path / "gmail.db")
    service = _FakeService(
        profile={"historyId": "1000"},
        list_pages=[{"messages": [{"id": "m1"}]}],
        get_responses={"m1": [_http_error(429, retry_after="1"), _raw_message("m1")]},
    )

    stats = run_sync(service, store)

    assert stats.messages_fetched == 1
    assert store.count_messages() == 1


def test_expired_history_id_falls_back_to_full_resync(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    store.set_sync_state("999")

    service = _FakeService(
        profile={"historyId": "2000"},
        history_pages=[_http_error(404)],
        list_pages=[{"messages": [{"id": "m1"}]}],
        get_responses={"m1": _raw_message("m1")},
    )

    stats = run_sync(service, store)

    assert stats.sync_type == "full"
    assert store.get_sync_state().last_history_id == "2000"


def test_permanent_error_during_fetch_propagates_without_retrying_forever(tmp_path):
    store = GmailStore(tmp_path / "gmail.db")
    service = _FakeService(
        profile={"historyId": "1000"},
        list_pages=[{"messages": [{"id": "m1"}]}],
        get_responses={"m1": _http_error(403, reason="insufficientPermissions")},
    )

    with pytest.raises(HttpError):
        run_sync(service, store)
