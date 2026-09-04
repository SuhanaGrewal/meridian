from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from meridian.security.validation import truncate_field


class MessageParseError(Exception):
    pass


@dataclass(frozen=True)
class ParsedMessage:
    message_id: str
    thread_id: str
    subject: str
    sender: str
    recipients: list[str]
    sent_at: str
    body_text: str
    label_ids: list[str]
    content_hash: str


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def parse_message(raw: dict[str, Any]) -> ParsedMessage:
    try:
        message_id = raw["id"]
        thread_id = raw["threadId"]
        payload = raw["payload"]
    except KeyError as exc:
        raise MessageParseError(f"missing required field: {exc}") from exc

    headers = _headers_dict(payload.get("headers", []))
    subject = truncate_field(headers.get("subject", ""))
    sender = headers.get("from", "")
    recipients = _split_addresses(headers.get("to", "")) + _split_addresses(headers.get("cc", ""))
    label_ids = raw.get("labelIds", [])

    sent_at = _extract_sent_at(raw, headers)
    body_text = truncate_field(_extract_body_text(payload))
    content_hash = _hash_content(subject, sender, recipients, body_text, label_ids)

    return ParsedMessage(
        message_id=message_id,
        thread_id=thread_id,
        subject=subject,
        sender=sender,
        recipients=recipients,
        sent_at=sent_at,
        body_text=body_text,
        label_ids=label_ids,
        content_hash=content_hash,
    )


def _headers_dict(headers: list[dict[str, str]]) -> dict[str, str]:
    return {h["name"].lower(): h.get("value", "") for h in headers if "name" in h}


def _split_addresses(value: str) -> list[str]:
    if not value:
        return []
    return [addr.strip() for addr in value.split(",") if addr.strip()]


def _extract_sent_at(raw: dict[str, Any], headers: dict[str, str]) -> str:
    internal_date = raw.get("internalDate")
    if internal_date is not None:
        try:
            timestamp_ms = int(internal_date)
            return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    return headers.get("date", "")


def _extract_body_text(payload: dict[str, Any]) -> str:
    plain = _find_part_body(payload, "text/plain")
    if plain is not None:
        return plain

    html = _find_part_body(payload, "text/html")
    if html is not None:
        return _strip_html(html)

    return ""


def _find_part_body(payload: dict[str, Any], mime_type: str) -> str | None:
    if payload.get("mimeType") == mime_type:
        data = payload.get("body", {}).get("data")
        if data:
            return _decode_base64url(data)

    for part in payload.get("parts", []) or []:
        found = _find_part_body(part, mime_type)
        if found is not None:
            return found

    return None


def _decode_base64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    return _HTML_TAG_RE.sub(" ", html).strip()


def _hash_content(
    subject: str, sender: str, recipients: list[str], body_text: str, label_ids: list[str]
) -> str:
    normalized = json.dumps(
        {
            "subject": subject,
            "sender": sender,
            "recipients": sorted(recipients),
            "body_text": body_text,
            "label_ids": sorted(label_ids),
        },
        sort_keys=True,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
