from __future__ import annotations

from typing import Any


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
