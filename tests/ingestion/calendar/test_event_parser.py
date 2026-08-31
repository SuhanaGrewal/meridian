from meridian.ingestion.calendar.event_parser import _extract_when


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
