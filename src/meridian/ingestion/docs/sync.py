from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from googleapiclient.errors import HttpError

from meridian.common.google_api import execute_with_retry
from meridian.common.rate_limiter import TokenBucket
from meridian.ingestion.docs.doc_parser import DocParseError, parse_document
from meridian.ingestion.docs.store import DocsStore

_DOC_MIME_TYPE = "application/vnd.google-apps.document"
_LIST_FIELDS = "nextPageToken, files(id, name, modifiedTime, trashed)"
_CHANGES_FIELDS = (
    "nextPageToken, newStartPageToken, "
    "changes(fileId, removed, file(id, name, mimeType, modifiedTime, trashed))"
)


@dataclass
class SyncStats:
    sync_type: str
    documents_fetched: int = 0
    documents_skipped_unchanged: int = 0
    documents_trashed: int = 0
    parse_failures: int = 0
    duration_ms: float = 0.0


def _fetch_and_store(
    docs_service,
    store: DocsStore,
    file_meta: dict,
    stats: SyncStats,
    *,
    rate_limiter: TokenBucket | None = None,
    logger: logging.Logger | None = None,
) -> None:
    doc_id = file_meta.get("id")
    if not doc_id:
        stats.parse_failures += 1
        if logger is not None:
            logger.warning(
                "skipping drive file with no id",
                extra={"operation": "docs.fetch_document", "status": "error", "duration_ms": 0},
            )
        return

    if file_meta.get("trashed"):
        store.mark_trashed(doc_id)
        stats.documents_trashed += 1
        return

    modified_time = file_meta.get("modifiedTime")
    if modified_time is not None and store.get_modified_time(doc_id) == modified_time:
        stats.documents_skipped_unchanged += 1
        return

    raw_document = execute_with_retry(
        docs_service.documents().get(documentId=doc_id),
        rate_limiter=rate_limiter,
        logger=logger,
        operation="docs.documents_get",
    )

    try:
        parsed = parse_document(raw_document, modified_time=modified_time)
    except DocParseError:
        stats.parse_failures += 1
        if logger is not None:
            logger.warning(
                f"failed to parse google doc {doc_id}",
                extra={"operation": "docs.parse_document", "status": "error", "duration_ms": 0},
            )
        return

    store.upsert_document(parsed)
    stats.documents_fetched += 1


def _full_backfill(
    drive_service,
    docs_service,
    store: DocsStore,
    *,
    rate_limiter: TokenBucket | None = None,
    logger: logging.Logger | None = None,
    drive_query: str = "",
) -> SyncStats:
    stats = SyncStats(sync_type="full")
    seen_doc_ids: set[str] = set()

    # captured before listing, mirroring gmail's getProfile()-before-list -
    # any doc that changes mid-backfill is simply picked up by the next
    # incremental sync instead of being missed.
    start_token_response = execute_with_retry(
        drive_service.changes().getStartPageToken(),
        rate_limiter=rate_limiter,
        logger=logger,
        operation="docs.get_start_page_token",
    )
    starting_page_token = start_token_response["startPageToken"]

    query = f"mimeType='{_DOC_MIME_TYPE}' and trashed=false"
    if drive_query:
        query += f" and ({drive_query})"

    page_token = None
    while True:
        response = execute_with_retry(
            drive_service.files().list(q=query, fields=_LIST_FIELDS, pageToken=page_token),
            rate_limiter=rate_limiter,
            logger=logger,
            operation="docs.files_list",
        )

        for file_meta in response.get("files", []):
            file_id = file_meta.get("id")
            if file_id:
                seen_doc_ids.add(file_id)
            _fetch_and_store(
                docs_service, store, file_meta, stats, rate_limiter=rate_limiter, logger=logger
            )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    stats.documents_trashed += store.tombstone_missing(seen_doc_ids)

    # persisted only after the full backfill (listing + reconciliation)
    # succeeds, so a crash midway safely redoes the whole thing next run.
    store.set_sync_state(starting_page_token)

    return stats


class _ChangesTokenInvalid(Exception):
    pass


def _incremental_sync(
    drive_service,
    docs_service,
    store: DocsStore,
    *,
    rate_limiter: TokenBucket | None = None,
    logger: logging.Logger | None = None,
    page_token: str,
) -> SyncStats:
    stats = SyncStats(sync_type="incremental")
    latest_page_token = page_token

    while True:
        request = drive_service.changes().list(pageToken=page_token, fields=_CHANGES_FIELDS)
        try:
            response = execute_with_retry(
                request,
                rate_limiter=rate_limiter,
                logger=logger,
                operation="docs.changes_list",
            )
        except HttpError as exc:
            # google does not document a specific status/reason for an
            # invalid changes.list page token (unlike calendar's documented
            # 410) - this call's only params are code-controlled, so a 400
            # here is treated as a best-effort signal the token expired.
            # falling back to a full resync is always correct regardless.
            if getattr(exc.resp, "status", None) == 400:
                raise _ChangesTokenInvalid() from exc
            raise

        for change in response.get("changes", []):
            _apply_change(docs_service, store, change, stats, rate_limiter=rate_limiter, logger=logger)

        latest_page_token = response.get("newStartPageToken", latest_page_token)
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    store.set_sync_state(latest_page_token)
    return stats


def _apply_change(
    docs_service,
    store: DocsStore,
    change: dict,
    stats: SyncStats,
    *,
    rate_limiter: TokenBucket | None,
    logger: logging.Logger | None,
) -> None:
    if change.get("removed"):
        file_id = change.get("fileId")
        if file_id:
            store.mark_trashed(file_id)
            stats.documents_trashed += 1
        return

    file_meta = change.get("file") or {}
    file_id = file_meta.get("id") or change.get("fileId")

    if file_meta.get("trashed"):
        if file_id:
            store.mark_trashed(file_id)
            stats.documents_trashed += 1
        return

    if file_meta.get("mimeType") != _DOC_MIME_TYPE:
        # a doc that's no longer a doc, or an unrelated drive file
        # surfacing in this drive-wide stream - only act if we actually
        # know about it locally.
        if file_id and store.get_modified_time(file_id) is not None:
            store.mark_trashed(file_id)
            stats.documents_trashed += 1
        return

    _fetch_and_store(docs_service, store, file_meta, stats, rate_limiter=rate_limiter, logger=logger)


def run_sync(
    drive_service,
    docs_service,
    store: DocsStore,
    *,
    rate_limiter: TokenBucket | None = None,
    logger: logging.Logger | None = None,
    drive_query: str = "",
) -> SyncStats:
    start = time.monotonic()
    sync_state = store.get_sync_state()

    if sync_state.page_token is None:
        stats = _full_backfill(
            drive_service,
            docs_service,
            store,
            rate_limiter=rate_limiter,
            logger=logger,
            drive_query=drive_query,
        )
    else:
        try:
            stats = _incremental_sync(
                drive_service,
                docs_service,
                store,
                rate_limiter=rate_limiter,
                logger=logger,
                page_token=sync_state.page_token,
            )
        except _ChangesTokenInvalid:
            if logger is not None:
                logger.warning(
                    "docs changes page token invalid/expired, falling back to full resync",
                    extra={"operation": "docs.sync", "status": "retry", "duration_ms": 0},
                )
            store.clear_sync_state()
            stats = _full_backfill(
                drive_service,
                docs_service,
                store,
                rate_limiter=rate_limiter,
                logger=logger,
                drive_query=drive_query,
            )

    stats.duration_ms = round((time.monotonic() - start) * 1000, 2)

    if logger is not None:
        logger.info(
            f"docs sync complete ({stats.sync_type})",
            extra={
                "operation": "docs.sync",
                "status": "success",
                "duration_ms": stats.duration_ms,
                "sync_type": stats.sync_type,
                "documents_fetched": stats.documents_fetched,
                "documents_skipped_unchanged": stats.documents_skipped_unchanged,
                "documents_trashed": stats.documents_trashed,
                "parse_failures": stats.parse_failures,
            },
        )

    return stats
