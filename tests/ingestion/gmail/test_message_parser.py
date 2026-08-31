import base64

import pytest

from meridian.ingestion.gmail.message_parser import MessageParseError, parse_message


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


def _headers(subject="Hello", sender="alice@example.com", to="bob@example.com", cc=None):
    headers = [
        {"name": "Subject", "value": subject},
        {"name": "From", "value": sender},
        {"name": "To", "value": to},
    ]
    if cc:
        headers.append({"name": "Cc", "value": cc})
    return headers


def test_parses_simple_plain_text_message():
    raw = {
        "id": "msg-1",
        "threadId": "thread-1",
        "labelIds": ["INBOX", "UNREAD"],
        "internalDate": "1700000000000",
        "payload": {
            "mimeType": "text/plain",
            "headers": _headers(),
            "body": {"data": _b64("Hello world")},
        },
    }

    parsed = parse_message(raw)

    assert parsed.message_id == "msg-1"
    assert parsed.thread_id == "thread-1"
    assert parsed.subject == "Hello"
    assert parsed.sender == "alice@example.com"
    assert parsed.recipients == ["bob@example.com"]
    assert parsed.body_text == "Hello world"
    assert parsed.label_ids == ["INBOX", "UNREAD"]
    assert parsed.sent_at.startswith("2023-")


def test_prefers_text_plain_over_text_html_when_both_present():
    raw = {
        "id": "msg-2",
        "threadId": "thread-2",
        "labelIds": [],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": _headers(),
            "parts": [
                {"mimeType": "text/html", "body": {"data": _b64("<p>HTML body</p>")}},
                {"mimeType": "text/plain", "body": {"data": _b64("Plain body")}},
            ],
        },
    }

    parsed = parse_message(raw)

    assert parsed.body_text == "Plain body"


def test_falls_back_to_stripped_html_when_no_plain_part():
    raw = {
        "id": "msg-3",
        "threadId": "thread-3",
        "labelIds": [],
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": _headers(),
            "parts": [
                {"mimeType": "text/html", "body": {"data": _b64("<p>Only <b>HTML</b> here</p>")}},
            ],
        },
    }

    parsed = parse_message(raw)

    assert "Only" in parsed.body_text
    assert "HTML" in parsed.body_text
    assert "<p>" not in parsed.body_text


def test_combines_to_and_cc_recipients():
    raw = {
        "id": "msg-4",
        "threadId": "thread-4",
        "labelIds": [],
        "payload": {
            "mimeType": "text/plain",
            "headers": _headers(to="bob@example.com, carol@example.com", cc="dave@example.com"),
            "body": {"data": _b64("hi")},
        },
    }

    parsed = parse_message(raw)

    assert parsed.recipients == ["bob@example.com", "carol@example.com", "dave@example.com"]


def test_missing_required_field_raises_message_parse_error():
    with pytest.raises(MessageParseError):
        parse_message({"id": "msg-5"})


def test_content_hash_changes_when_body_changes():
    base = {
        "id": "msg-6",
        "threadId": "thread-6",
        "labelIds": [],
        "payload": {
            "mimeType": "text/plain",
            "headers": _headers(),
            "body": {"data": _b64("version one")},
        },
    }
    changed = {**base, "payload": {**base["payload"], "body": {"data": _b64("version two")}}}

    hash_one = parse_message(base).content_hash
    hash_two = parse_message(changed).content_hash

    assert hash_one != hash_two
