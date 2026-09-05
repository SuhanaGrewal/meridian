from __future__ import annotations

import re
from datetime import date, timedelta

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_STRIP_PREFIX_RE = re.compile(r"^(by|before|on|until)\s+", re.IGNORECASE)
_IN_N_DAYS_RE = re.compile(r"^in (\d+) days?$", re.IGNORECASE)


def _next_or_same_weekday(anchor: date, target_weekday: int) -> date:
    days_ahead = (target_weekday - anchor.weekday()) % 7
    return anchor + timedelta(days=days_ahead)


def resolve_deadline_phrase(phrase: str | None, anchor: date) -> date | None:
    """resolves a relative deadline phrase (as extracted by the LLM from a
    message's text, e.g. "by Friday") into an absolute date, anchored to
    when the message was actually sent - not "now." This is deliberately
    NOT delegated to the LLM: asking it to also resolve the date reintroduces
    the same unreliable-arithmetic failure mode found in query answering
    (query/prompt.py's _relative_days_label) - the LLM should only extract
    the phrase verbatim, and this function does the arithmetic
    deterministically. Returns None for anything unrecognized rather than
    guessing - a missing due date is safer than a wrong one."""
    if not phrase:
        return None
    text = phrase.strip().lower()
    if text in ("", "none"):
        return None
    text = _STRIP_PREFIX_RE.sub("", text)

    if text in ("today", "end of day", "eod", "tonight"):
        return anchor
    if text == "tomorrow":
        return anchor + timedelta(days=1)
    if text in ("end of week", "eow", "this week"):
        return _next_or_same_weekday(anchor, 4)  # friday
    if text == "next week":
        return anchor + timedelta(days=7)

    match = _IN_N_DAYS_RE.match(text)
    if match:
        return anchor + timedelta(days=int(match.group(1)))

    for index, name in enumerate(_WEEKDAYS):
        if name in text:
            return _next_or_same_weekday(anchor, index)

    return None
