from __future__ import annotations

import json
from email.utils import parseaddr
from typing import Any, Literal

Relationship = Literal["new", "occasional", "frequent"]

# thresholds are a simple, tunable heuristic, not a scientific measure -
# they only need to be good enough to steer tone (a first-time contact
# reads more formal, a frequent one more casual), not to model the
# relationship precisely.
_OCCASIONAL_THRESHOLD = 1
_FREQUENT_THRESHOLD = 5


def _message_involves(row: Any, contact_email: str) -> bool:
    _, sender_email = parseaddr(row["sender"] or "")
    if sender_email.lower() == contact_email:
        return True
    for raw in json.loads(row["recipients"] or "[]"):
        _, recipient_email = parseaddr(raw or "")
        if recipient_email.lower() == contact_email:
            return True
    return False


def classify_relationship(gmail_store: Any, contact_email: str, *, exclude_message_id: str | None = None) -> Relationship:
    """counts how many past messages (either direction - sent to or
    received from) exchanged with this contact, across the whole mailbox,
    and buckets it into a coarse relationship signal used to steer a
    drafted reply's formality. Deterministic counting, not an LLM
    judgment - the same "prefer reliable code over LLM guessing" approach
    this project already applies to dates and deadlines.

    exclude_message_id should be the message currently being replied to -
    without excluding it, that message alone would always count as at
    least one prior exchange, so a genuine first-time contact could never
    come back as "new"."""
    contact_email = contact_email.strip().lower()
    if not contact_email:
        return "new"

    count = sum(
        1
        for row in gmail_store.get_all_messages()
        if row["message_id"] != exclude_message_id and _message_involves(row, contact_email)
    )

    if count >= _FREQUENT_THRESHOLD:
        return "frequent"
    if count >= _OCCASIONAL_THRESHOLD:
        return "occasional"
    return "new"
