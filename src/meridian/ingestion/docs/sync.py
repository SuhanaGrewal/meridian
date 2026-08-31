from __future__ import annotations

import logging
from dataclasses import dataclass

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
