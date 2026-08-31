from __future__ import annotations

import logging
from dataclasses import dataclass

from googleapiclient.errors import HttpError

from meridian.common.google_api import execute_with_retry
from meridian.common.rate_limiter import TokenBucket
from meridian.ingestion.calendar.event_parser import EventParseError, parse_event
from meridian.ingestion.calendar.store import CalendarStore

# must stay identical between the sync-token-issuing call and every
# subsequent call using that token, or google errors.
SINGLE_EVENTS = True

# required for incremental sync to receive status="cancelled" deletion
# notices at all - calendar has no separate deletions-only mechanism.
SHOW_DELETED = True


@dataclass
class SyncStats:
    sync_type: str
    events_fetched: int = 0
    events_deleted: int = 0
    events_reconciled_deleted: int = 0
    parse_failures: int = 0
    duration_ms: float = 0.0


def _store_item(
    store: CalendarStore,
    calendar_id: str,
    raw: dict,
    stats: SyncStats,
    logger: logging.Logger | None = None,
) -> None:
    event_id = raw.get("id")

    if raw.get("status") == "cancelled" and event_id:
        store.mark_deleted(calendar_id, event_id)
        stats.events_deleted += 1
        return

    try:
        parsed = parse_event(raw, calendar_id=calendar_id)
    except EventParseError:
        stats.parse_failures += 1
        if logger is not None:
            logger.warning(
                f"failed to parse calendar event {event_id}",
                extra={"operation": "calendar.parse_event", "status": "error", "duration_ms": 0},
            )
        return

    store.upsert_event(parsed)
    stats.events_fetched += 1


def _full_backfill(
    service,
    store: CalendarStore,
    *,
    calendar_id: str,
    rate_limiter: TokenBucket | None,
    logger: logging.Logger | None,
    time_min: str | None,
) -> SyncStats:
    stats = SyncStats(sync_type="full")
    seen_event_ids: set[str] = set()
    sync_token: str | None = None

    page_token = None
    while True:
        list_kwargs = dict(
            calendarId=calendar_id,
            singleEvents=SINGLE_EVENTS,
            showDeleted=SHOW_DELETED,
            maxResults=250,
            pageToken=page_token,
        )
        if time_min:
            list_kwargs["timeMin"] = time_min

        response = execute_with_retry(
            service.events().list(**list_kwargs),
            rate_limiter=rate_limiter,
            logger=logger,
            operation="calendar.events_list",
        )

        for raw in response.get("items", []):
            event_id = raw.get("id")
            if event_id:
                seen_event_ids.add(event_id)
            _store_item(store, calendar_id, raw, stats, logger)

        sync_token = response.get("nextSyncToken", sync_token)
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    stats.events_reconciled_deleted = store.tombstone_missing(
        calendar_id, seen_event_ids, min_start_at=time_min
    )

    if sync_token:
        store.set_sync_state(calendar_id, sync_token)

    return stats


class _SyncTokenExpired(Exception):
    pass


def _incremental_sync(
    service,
    store: CalendarStore,
    *,
    calendar_id: str,
    rate_limiter: TokenBucket | None,
    logger: logging.Logger | None,
    sync_token: str,
) -> SyncStats:
    stats = SyncStats(sync_type="incremental")
    latest_sync_token = sync_token

    page_token = None
    while True:
        # note: syncToken can never be combined with timeMin/timeMax/q -
        # google returns a 400 error if you try.
        request = service.events().list(
            calendarId=calendar_id,
            syncToken=sync_token,
            singleEvents=SINGLE_EVENTS,
            showDeleted=SHOW_DELETED,
            pageToken=page_token,
        )
        try:
            response = execute_with_retry(
                request,
                rate_limiter=rate_limiter,
                logger=logger,
                operation="calendar.events_list",
            )
        except HttpError as exc:
            if getattr(exc.resp, "status", None) == 410:
                raise _SyncTokenExpired() from exc
            raise

        for raw in response.get("items", []):
            _store_item(store, calendar_id, raw, stats, logger)

        latest_sync_token = response.get("nextSyncToken", latest_sync_token)
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    store.set_sync_state(calendar_id, latest_sync_token)
    return stats
