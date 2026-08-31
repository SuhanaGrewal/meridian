from __future__ import annotations

import logging
from dataclasses import dataclass

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
