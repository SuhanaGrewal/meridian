import pytest

from meridian.ingestion.calendar.event_parser import (
    EventParseError,
    _extract_attendees,
    _extract_organizer_email,
    _extract_when,
    parse_event,
)


def test_extract_when_all_day_event():
    when, is_all_day = _extract_when({"date": "2024-06-01"})

    assert when == "2024-06-01"
    assert is_all_day is True


def test_extract_when_timed_event():
    when, is_all_day = _extract_when(
        {"dateTime": "2024-06-01T10:00:00-05:00", "timeZone": "America/New_York"}
    )

    assert when == "2024-06-01T10:00:00-05:00"
    assert is_all_day is False


def test_extract_when_missing_node_returns_none():
    when, is_all_day = _extract_when(None)

    assert when is None
    assert is_all_day is False


def test_extract_when_empty_node_returns_none():
    when, is_all_day = _extract_when({})

    assert when is None
    assert is_all_day is False


def test_extract_attendees_normalizes_fields():
    raw = {
        "attendees": [
            {"email": "alice@example.com", "displayName": "Alice", "responseStatus": "accepted"},
            {"email": "bob@example.com"},
        ]
    }

    attendees = _extract_attendees(raw)

    assert attendees == [
        {"email": "alice@example.com", "display_name": "Alice", "response_status": "accepted"},
        {"email": "bob@example.com", "display_name": None, "response_status": None},
    ]


def test_extract_attendees_missing_key_returns_empty_list():
    assert _extract_attendees({}) == []


def test_extract_organizer_email():
    assert _extract_organizer_email({"organizer": {"email": "alice@example.com"}}) == "alice@example.com"


def test_extract_organizer_email_missing_returns_none():
    assert _extract_organizer_email({}) is None


def test_parse_event_extracts_timed_event():
    raw = {
        "id": "evt-1",
        "iCalUID": "evt-1@google.com",
        "status": "confirmed",
        "summary": "Standup",
        "description": "Daily sync",
        "location": "Room 1",
        "start": {"dateTime": "2024-06-01T10:00:00-05:00"},
        "end": {"dateTime": "2024-06-01T10:30:00-05:00"},
        "organizer": {"email": "alice@example.com"},
        "attendees": [{"email": "bob@example.com", "responseStatus": "accepted"}],
        "updated": "2024-05-01T00:00:00.000Z",
    }

    parsed = parse_event(raw, calendar_id="primary")

    assert parsed.calendar_id == "primary"
    assert parsed.event_id == "evt-1"
    assert parsed.ical_uid == "evt-1@google.com"
    assert parsed.summary == "Standup"
    assert parsed.description == "Daily sync"
    assert parsed.location == "Room 1"
    assert parsed.status == "confirmed"
    assert parsed.start_at == "2024-06-01T10:00:00-05:00"
    assert parsed.end_at == "2024-06-01T10:30:00-05:00"
    assert parsed.is_all_day is False
    assert parsed.organizer_email == "alice@example.com"
    assert parsed.attendees == [
        {"email": "bob@example.com", "display_name": None, "response_status": "accepted"}
    ]
    assert parsed.source_updated_at == "2024-05-01T00:00:00.000Z"


def test_parse_event_extracts_all_day_event():
    raw = {
        "id": "evt-2",
        "start": {"date": "2024-06-01"},
        "end": {"date": "2024-06-02"},
    }

    parsed = parse_event(raw, calendar_id="primary")

    assert parsed.is_all_day is True
    assert parsed.start_at == "2024-06-01"


def test_parse_event_tolerates_missing_optional_fields():
    parsed = parse_event({"id": "evt-3"}, calendar_id="primary")

    assert parsed.summary == ""
    assert parsed.description == ""
    assert parsed.location == ""
    assert parsed.status == "confirmed"
    assert parsed.start_at is None
    assert parsed.end_at is None
    assert parsed.organizer_email is None
    assert parsed.attendees == []


def test_parse_event_tolerates_cancelled_stub():
    parsed = parse_event({"id": "evt-4", "status": "cancelled"}, calendar_id="primary")

    assert parsed.status == "cancelled"
    assert parsed.summary == ""


def test_parse_event_missing_id_raises_event_parse_error():
    with pytest.raises(EventParseError):
        parse_event({"summary": "no id here"}, calendar_id="primary")


def test_oversized_free_text_fields_are_truncated():
    from meridian.security.validation import MAX_FIELD_CHARS

    raw = {
        "id": "evt-5",
        "summary": "s" * (MAX_FIELD_CHARS + 1000),
        "description": "d" * (MAX_FIELD_CHARS + 1000),
        "location": "l" * (MAX_FIELD_CHARS + 1000),
    }

    parsed = parse_event(raw, calendar_id="primary")

    assert len(parsed.summary) == MAX_FIELD_CHARS
    assert len(parsed.description) == MAX_FIELD_CHARS
    assert len(parsed.location) == MAX_FIELD_CHARS


def test_normal_sized_free_text_fields_are_unaffected_by_truncation():
    raw = {"id": "evt-6", "summary": "Standup", "description": "daily sync", "location": "Room A"}

    parsed = parse_event(raw, calendar_id="primary")

    assert parsed.summary == "Standup"
    assert parsed.description == "daily sync"
    assert parsed.location == "Room A"
