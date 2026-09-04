from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from meridian.security.validation import truncate_field


class EventParseError(Exception):
    pass


@dataclass(frozen=True)
class ParsedEvent:
    calendar_id: str
    event_id: str
    ical_uid: str | None
    recurring_event_id: str | None
    summary: str
    description: str
    location: str
    status: str
    start_at: str | None
    end_at: str | None
    is_all_day: bool
    organizer_email: str | None
    attendees: list[dict[str, Any]]
    source_updated_at: str | None


def parse_event(raw: dict[str, Any], *, calendar_id: str) -> ParsedEvent:
    try:
        event_id = raw["id"]
    except KeyError as exc:
        raise EventParseError(f"missing required field: {exc}") from exc

    start_at, is_all_day_start = _extract_when(raw.get("start"))
    end_at, _ = _extract_when(raw.get("end"))

    return ParsedEvent(
        calendar_id=calendar_id,
        event_id=event_id,
        ical_uid=raw.get("iCalUID"),
        recurring_event_id=raw.get("recurringEventId"),
        summary=truncate_field(raw.get("summary", "")),
        description=truncate_field(raw.get("description", "")),
        location=truncate_field(raw.get("location", "")),
        status=raw.get("status", "confirmed"),
        start_at=start_at,
        end_at=end_at,
        is_all_day=is_all_day_start,
        organizer_email=_extract_organizer_email(raw),
        attendees=_extract_attendees(raw),
        source_updated_at=raw.get("updated"),
    )


def _extract_when(node: dict[str, Any] | None) -> tuple[str | None, bool]:
    """extracts a start/end node ({'date': ...} or {'dateTime': ...}) into (iso_string, is_all_day)."""
    if not node:
        return None, False
    if "date" in node:
        return node["date"], True
    if "dateTime" in node:
        return node["dateTime"], False
    return None, False


def _extract_attendees(raw: dict[str, Any]) -> list[dict[str, Any]]:
    attendees = raw.get("attendees") or []
    return [
        {
            "email": attendee.get("email"),
            "display_name": attendee.get("displayName"),
            "response_status": attendee.get("responseStatus"),
        }
        for attendee in attendees
    ]


def _extract_organizer_email(raw: dict[str, Any]) -> str | None:
    organizer = raw.get("organizer") or {}
    return organizer.get("email")
