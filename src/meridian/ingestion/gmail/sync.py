from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from googleapiclient.errors import HttpError

from meridian.common.google_api import execute_with_retry
from meridian.common.rate_limiter import TokenBucket
from meridian.ingestion.gmail.message_parser import MessageParseError, parse_message
from meridian.ingestion.gmail.store import GmailStore

_HISTORY_TYPES = ["messageAdded", "messageDeleted", "labelAdded", "labelRemoved"]


@dataclass
class SyncStats:
    sync_type: str
    messages_fetched: int = 0
    messages_updated: int = 0
    messages_deleted: int = 0
    parse_failures: int = 0
    duration_ms: float = 0.0


class _HistoryExpired(Exception):
    pass


def run_sync(
    service,
    store: GmailStore,
    *,
    rate_limiter: TokenBucket | None = None,
    logger: logging.Logger | None = None,
    query: str = "",
) -> SyncStats:
    start = time.monotonic()
    sync_state = store.get_sync_state()

    if sync_state.last_history_id is None:
        stats = _full_backfill(service, store, rate_limiter=rate_limiter, logger=logger, query=query)
    else:
        try:
            stats = _incremental_sync(
                service,
                store,
                rate_limiter=rate_limiter,
                logger=logger,
                last_history_id=sync_state.last_history_id,
            )
        except _HistoryExpired:
            if logger is not None:
                logger.warning(
                    "gmail history id expired, falling back to full resync",
                    extra={"operation": "gmail.sync", "status": "retry", "duration_ms": 0},
                )
            stats = _full_backfill(service, store, rate_limiter=rate_limiter, logger=logger, query=query)

    stats.duration_ms = round((time.monotonic() - start) * 1000, 2)

    if logger is not None:
        logger.info(
            f"gmail sync complete ({stats.sync_type})",
            extra={
                "operation": "gmail.sync",
                "status": "success",
                "duration_ms": stats.duration_ms,
                "sync_type": stats.sync_type,
                "messages_fetched": stats.messages_fetched,
                "messages_updated": stats.messages_updated,
                "messages_deleted": stats.messages_deleted,
                "parse_failures": stats.parse_failures,
            },
        )

    return stats


def _full_backfill(service, store, *, rate_limiter, logger, query: str) -> SyncStats:
    stats = SyncStats(sync_type="full")

    profile = execute_with_retry(
        service.users().getProfile(userId="me"),
        rate_limiter=rate_limiter,
        logger=logger,
        operation="gmail.get_profile",
    )
    starting_history_id = profile["historyId"]

    page_token = None
    while True:
        response = execute_with_retry(
            service.users().messages().list(userId="me", q=query, pageToken=page_token, maxResults=100),
            rate_limiter=rate_limiter,
            logger=logger,
            operation="gmail.messages_list",
        )
        for item in response.get("messages", []):
            _fetch_and_store(service, store, item["id"], stats, rate_limiter=rate_limiter, logger=logger)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    store.set_sync_state(starting_history_id)
    return stats


def _incremental_sync(service, store, *, rate_limiter, logger, last_history_id: str) -> SyncStats:
    stats = SyncStats(sync_type="incremental")

    page_token = None
    latest_history_id = last_history_id
    while True:
        request = service.users().history().list(
            userId="me",
            startHistoryId=last_history_id,
            historyTypes=_HISTORY_TYPES,
            pageToken=page_token,
        )
        try:
            response = execute_with_retry(
                request,
                rate_limiter=rate_limiter,
                logger=logger,
                operation="gmail.history_list",
            )
        except HttpError as exc:
            if getattr(exc.resp, "status", None) == 404:
                raise _HistoryExpired() from exc
            raise

        for record in response.get("history", []):
            for added in record.get("messagesAdded", []):
                message_id = added["message"]["id"]
                _fetch_and_store(service, store, message_id, stats, rate_limiter=rate_limiter, logger=logger)

            for changed in record.get("labelsAdded", []) + record.get("labelsRemoved", []):
                message = changed["message"]
                store.update_labels(message["id"], message.get("labelIds", []))
                stats.messages_updated += 1

            for deleted in record.get("messagesDeleted", []):
                store.mark_deleted(deleted["message"]["id"])
                stats.messages_deleted += 1

        latest_history_id = response.get("historyId", latest_history_id)
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    store.set_sync_state(latest_history_id)
    return stats


def _fetch_and_store(service, store, message_id: str, stats: SyncStats, *, rate_limiter, logger) -> None:
    try:
        raw = execute_with_retry(
            service.users().messages().get(userId="me", id=message_id, format="full"),
            rate_limiter=rate_limiter,
            logger=logger,
            operation="gmail.messages_get",
        )
    except HttpError as exc:
        if getattr(exc.resp, "status", None) == 404:
            # Message was deleted between the history event and our fetch —
            # a benign race, not a parse failure.
            store.mark_deleted(message_id)
            stats.messages_deleted += 1
            return
        raise

    try:
        parsed = parse_message(raw)
    except MessageParseError as exc:
        store.record_dead_letter(message_id, str(exc))
        stats.parse_failures += 1
        if logger is not None:
            logger.warning(
                f"failed to parse gmail message {message_id}",
                extra={"operation": "gmail.parse_message", "status": "error", "duration_ms": 0},
            )
        return

    store.upsert_message(parsed)
    stats.messages_fetched += 1
