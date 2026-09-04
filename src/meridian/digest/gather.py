from __future__ import annotations

import logging
from typing import Any

from meridian.digest.state import GatheredItem

_DETAIL_CHARS = 500


def _gmail_item(row: Any) -> GatheredItem:
    return {
        "source": "gmail",
        "label": f"Gmail email from {row['sender']}, sent {row['sent_at']}, subject: '{row['subject']}'",
        "detail": (row["body_text"] or "")[:_DETAIL_CHARS],
    }


def _calendar_item(row: Any) -> GatheredItem:
    return {
        "source": "calendar",
        "label": f"Calendar event '{row['summary']}' starting {row['start_at']}",
        "detail": (row["description"] or "")[:_DETAIL_CHARS],
    }


def _docs_item(row: Any) -> GatheredItem:
    return {
        "source": "docs",
        "label": f"Google Doc titled '{row['title']}', modified {row['modified_time']}",
        "detail": (row["content_text"] or "")[:_DETAIL_CHARS],
    }


def _notes_item(row: Any) -> GatheredItem:
    return {
        "source": "local_files",
        "label": f"Note file at {row['path']}, updated {row['updated_at']}",
        "detail": (row["content_text"] or "")[:_DETAIL_CHARS],
    }


def _entity_item(row: Any) -> GatheredItem:
    return {
        "source": "entity",
        "label": f"{row['display_name']} ({row['entity_type']}) mentioned {row['mention_count']} time(s)",
        "detail": "",
    }


def gather_items(
    gmail_store: Any,
    calendar_store: Any,
    docs_store: Any,
    notes_store: Any,
    entity_store: Any,
    *,
    since: str,
    now: str,
    lookahead_end: str,
    logger: logging.Logger | None = None,
) -> list[GatheredItem]:
    """pulls raw new/changed/upcoming content directly from each source's
    own store - no search, embeddings, or reranking involved. gmail/docs/
    notes/entities are backward-looking (what changed since `since`);
    calendar is forward-looking (what's upcoming between `now` and
    `lookahead_end`), since that's what's actually useful in a personal
    digest."""
    items: list[GatheredItem] = []
    items += [_gmail_item(row) for row in gmail_store.list_messages_since(since)]
    items += [_calendar_item(row) for row in calendar_store.list_events_upcoming(now, lookahead_end)]
    items += [_docs_item(row) for row in docs_store.list_docs_modified_since(since)]
    items += [_notes_item(row) for row in notes_store.list_notes_updated_since(since)]
    items += [_entity_item(row) for row in entity_store.list_entities_mentioned_since(since)]

    if logger is not None:
        logger.info(
            "digest gather complete",
            extra={
                "operation": "digest.gather",
                "status": "success",
                "duration_ms": 0,
                "item_count": len(items),
            },
        )
    return items
