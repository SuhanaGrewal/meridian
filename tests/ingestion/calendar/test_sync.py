import json

import httplib2
import pytest
from googleapiclient.errors import HttpError

from meridian.ingestion.calendar.event_parser import parse_event
from meridian.ingestion.calendar.store import CalendarStore
from meridian.ingestion.calendar.sync import (
    SyncStats,
    _full_backfill,
    _incremental_sync,
    _store_item,
    _SyncTokenExpired,
)


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
    """mimics retrying the *same* request object's .execute() across attempts."""

    def __init__(self, outcomes: list):
        self._outcomes = outcomes

    def execute(self):
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeEvents:
    def __init__(self, list_pages):
        self._list_pages = [
            (page if isinstance(page, list) else [page]) for page in list_pages
        ]
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        outcomes = self._list_pages.pop(0)
        return _QueuedRequest(outcomes) if len(outcomes) > 1 else _Request(outcomes[0])


class _FakeCalendarService:
    def __init__(self, *, list_pages=None):
        self.events_double = _FakeEvents(list_pages or [])

    def events(self):
        return self.events_double


def _raw_event(event_id: str, **overrides) -> dict:
    raw = {
        "id": event_id,
        "status": "confirmed",
        "summary": f"Event {event_id}",
        "start": {"dateTime": "2024-06-01T10:00:00-05:00"},
        "end": {"dateTime": "2024-06-01T10:30:00-05:00"},
    }
    raw.update(overrides)
    return raw


def test_store_item_upserts_a_confirmed_event(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    stats = SyncStats(sync_type="full")

    _store_item(store, "primary", _raw_event("evt-1"), stats)

    assert stats.events_fetched == 1
    assert store.count_events() == 1


def test_store_item_marks_cancelled_event_as_deleted(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    stats = SyncStats(sync_type="incremental")
    store.upsert_event(parse_event(_raw_event("evt-1"), calendar_id="primary"))

    _store_item(store, "primary", {"id": "evt-1", "status": "cancelled"}, stats)

    assert stats.events_deleted == 1
    assert store.get_event_row("primary", "evt-1")["is_deleted"] == 1


def test_store_item_dead_letters_malformed_event_without_id(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    stats = SyncStats(sync_type="full")

    _store_item(store, "primary", {"summary": "no id"}, stats)

    assert stats.parse_failures == 1
    assert store.count_events() == 0


def test_full_backfill_stores_events_and_persists_sync_token(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    service = _FakeCalendarService(
        list_pages=[{"items": [_raw_event("evt-1"), _raw_event("evt-2")], "nextSyncToken": "token-1"}]
    )

    stats = _full_backfill(
        service, store, calendar_id="primary", rate_limiter=None, logger=None, time_min=None
    )

    assert stats.sync_type == "full"
    assert stats.events_fetched == 2
    assert store.count_events() == 2
    assert store.get_sync_state("primary").sync_token == "token-1"


def test_full_backfill_paginates_across_multiple_pages(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    service = _FakeCalendarService(
        list_pages=[
            {"items": [_raw_event("evt-1")], "nextPageToken": "p2"},
            {"items": [_raw_event("evt-2")], "nextSyncToken": "token-1"},
        ]
    )

    stats = _full_backfill(
        service, store, calendar_id="primary", rate_limiter=None, logger=None, time_min=None
    )

    assert stats.events_fetched == 2
    assert store.count_events() == 2


def test_full_backfill_passes_time_min_only_when_set(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    service = _FakeCalendarService(list_pages=[{"items": []}])

    _full_backfill(
        service,
        store,
        calendar_id="primary",
        rate_limiter=None,
        logger=None,
        time_min="2024-01-01T00:00:00Z",
    )

    assert service.events_double.list_calls[0]["timeMin"] == "2024-01-01T00:00:00Z"


def test_full_backfill_omits_time_min_when_unset(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    service = _FakeCalendarService(list_pages=[{"items": []}])

    _full_backfill(service, store, calendar_id="primary", rate_limiter=None, logger=None, time_min=None)

    assert "timeMin" not in service.events_double.list_calls[0]


def test_full_backfill_is_idempotent_when_rerun(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    page = {"items": [_raw_event("evt-1")], "nextSyncToken": "token-1"}

    service_one = _FakeCalendarService(list_pages=[dict(page)])
    _full_backfill(service_one, store, calendar_id="primary", rate_limiter=None, logger=None, time_min=None)

    service_two = _FakeCalendarService(list_pages=[dict(page)])
    _full_backfill(service_two, store, calendar_id="primary", rate_limiter=None, logger=None, time_min=None)

    assert store.count_events() == 1


def test_full_backfill_tombstones_event_missing_from_fresh_listing(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    store.upsert_event(parse_event(_raw_event("evt-stale"), calendar_id="primary"))

    service = _FakeCalendarService(
        list_pages=[{"items": [_raw_event("evt-1")], "nextSyncToken": "token-1"}]
    )
    stats = _full_backfill(
        service, store, calendar_id="primary", rate_limiter=None, logger=None, time_min=None
    )

    assert stats.events_reconciled_deleted == 1
    assert store.get_event_row("primary", "evt-stale")["is_deleted"] == 1


def test_incremental_sync_uses_stored_sync_token(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    service = _FakeCalendarService(
        list_pages=[{"items": [_raw_event("evt-1")], "nextSyncToken": "token-2"}]
    )

    stats = _incremental_sync(
        service, store, calendar_id="primary", rate_limiter=None, logger=None, sync_token="token-1"
    )

    assert stats.sync_type == "incremental"
    assert stats.events_fetched == 1
    assert service.events_double.list_calls[0]["syncToken"] == "token-1"
    assert store.get_sync_state("primary").sync_token == "token-2"


def test_incremental_sync_never_sends_time_bound_params(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    service = _FakeCalendarService(list_pages=[{"items": [], "nextSyncToken": "token-2"}])

    _incremental_sync(
        service, store, calendar_id="primary", rate_limiter=None, logger=None, sync_token="token-1"
    )

    call_kwargs = service.events_double.list_calls[0]
    assert "timeMin" not in call_kwargs
    assert "timeMax" not in call_kwargs
    assert "q" not in call_kwargs


def test_incremental_sync_paginates_across_multiple_pages(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    service = _FakeCalendarService(
        list_pages=[
            {"items": [_raw_event("evt-1")], "nextPageToken": "p2"},
            {"items": [_raw_event("evt-2")], "nextSyncToken": "token-2"},
        ]
    )

    stats = _incremental_sync(
        service, store, calendar_id="primary", rate_limiter=None, logger=None, sync_token="token-1"
    )

    assert stats.events_fetched == 2
    assert store.get_sync_state("primary").sync_token == "token-2"


def test_incremental_sync_tombstones_cancelled_event(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    store.upsert_event(parse_event(_raw_event("evt-1"), calendar_id="primary"))
    service = _FakeCalendarService(
        list_pages=[
            {"items": [{"id": "evt-1", "status": "cancelled"}], "nextSyncToken": "token-2"}
        ]
    )

    stats = _incremental_sync(
        service, store, calendar_id="primary", rate_limiter=None, logger=None, sync_token="token-1"
    )

    assert stats.events_deleted == 1
    assert store.get_event_row("primary", "evt-1")["is_deleted"] == 1


def test_incremental_sync_expired_token_raises_sync_token_expired(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    service = _FakeCalendarService(list_pages=[_http_error(410)])

    with pytest.raises(_SyncTokenExpired):
        _incremental_sync(
            service, store, calendar_id="primary", rate_limiter=None, logger=None, sync_token="token-1"
        )


def test_incremental_sync_permanent_error_propagates(tmp_path):
    store = CalendarStore(tmp_path / "calendar.db")
    service = _FakeCalendarService(list_pages=[_http_error(403, reason="insufficientPermissions")])

    with pytest.raises(HttpError):
        _incremental_sync(
            service, store, calendar_id="primary", rate_limiter=None, logger=None, sync_token="token-1"
        )


def test_incremental_sync_rate_limited_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr("meridian.common.google_api.time.sleep", lambda s: None)
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: None)

    store = CalendarStore(tmp_path / "calendar.db")
    service = _FakeCalendarService(
        list_pages=[
            [_http_error(429, retry_after="1"), {"items": [_raw_event("evt-1")], "nextSyncToken": "token-2"}]
        ]
    )

    stats = _incremental_sync(
        service, store, calendar_id="primary", rate_limiter=None, logger=None, sync_token="token-1"
    )

    assert stats.events_fetched == 1
