from __future__ import annotations

from email.utils import parseaddr
from typing import Any

_DEFAULT_LIMIT = 5
_DEFAULT_MIN_CHARS = 40
_EXAMPLE_CHARS = 500  # matches digest/gather.py's own detail-truncation length


def sample_voice_examples(
    gmail_store: Any, account_email: str, *, limit: int = _DEFAULT_LIMIT, min_chars: int = _DEFAULT_MIN_CHARS
) -> list[str]:
    """pulls the user's own most recent substantive sent messages as
    style examples for drafting - not a trained "voice model," just real
    excerpts handed to the LLM as few-shot context, the same "let the LLM
    see real examples rather than a hand-built profile" approach used
    nowhere else in this project only because nothing else needed a
    writing-style signal before. Messages under min_chars are skipped
    (a one-line "Thanks!" doesn't teach anything about how the user
    writes a substantive reply) and each is truncated to _EXAMPLE_CHARS
    to bound how much of the prompt this eats."""
    account_email = account_email.strip().lower()
    sent = []
    for row in gmail_store.get_all_messages():
        _, sender_email = parseaddr(row["sender"] or "")
        if sender_email.lower() != account_email:
            continue
        body = (row["body_text"] or "").strip()
        if len(body) < min_chars:
            continue
        sent.append(row)

    sent.sort(key=lambda row: row["sent_at"] or "", reverse=True)
    return [(row["body_text"] or "")[:_EXAMPLE_CHARS] for row in sent[:limit]]
