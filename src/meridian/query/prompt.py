from __future__ import annotations

from datetime import datetime, timezone

from meridian.query.date_range import parse_stored_date
from meridian.query.retrieval import RetrievedChunk

# fixed constant, contains no user data - never tokenized before an
# external call, unlike the user message built from real retrieved content.
SYSTEM_PROMPT = (
    "You are a personal knowledge assistant. Answer the user's question using "
    "ONLY the numbered context blocks provided below the question - never rely "
    "on outside knowledge. After each claim, cite the bracket number(s) of the "
    "context block(s) it came from, like [1] or [1][2]. If the provided context "
    "does not contain enough information to answer, say so plainly instead of "
    "guessing.\n\n"
    "Dated items (emails, calendar events) are labeled with how long ago or "
    "from now they are, like \"(115 days ago)\" or \"(in 3 days)\" - trust "
    "that label directly rather than computing it yourself from today's date "
    "(also given at the top of the context). If the question implies the "
    "user wants something current or upcoming (e.g. \"what flights do I "
    "have,\" \"what's my next X\") and everything relevant is labeled \"ago\" "
    "(in the past), say plainly that there's nothing upcoming - don't present "
    "a past item as if it were still pending just because it's the most "
    "recent one found. You may still separately mention the most recent past "
    "item as context, making clear it has already happened.\n\n"
    "Some names, email addresses, phone numbers, and addresses in the context "
    "have been replaced with placeholders like <PERSON_1>, <EMAIL_ADDRESS_1>, "
    "<PHONE_NUMBER_1>, or <HOME_ADDRESS_1> to protect privacy. Treat these "
    "exactly like real names/emails/etc. in your answer - use them naturally in "
    "place of the real values, and do not comment on or explain the "
    "placeholders themselves."
)


def _relative_days_label(date_str: str, now: datetime) -> str:
    """computed deterministically in code, not left for the model to work
    out - an llm asked to do date arithmetic against a "today's date" line
    is unreliable in practice (confirmed: it correctly called one past item
    "past" and incorrectly called another, equally past, item "upcoming" in
    the same response). Handing it the already-computed answer removes that
    failure mode entirely."""
    parsed = parse_stored_date(date_str)
    if parsed is None:
        return ""
    delta_days = (now - parsed).days
    if delta_days > 0:
        return f" ({delta_days} day{'s' if delta_days != 1 else ''} ago)"
    if delta_days < 0:
        future_days = -delta_days
        return f" (in {future_days} day{'s' if future_days != 1 else ''})"
    return " (today)"


def _source_label(chunk: RetrievedChunk, *, now: datetime | None = None) -> str:
    now = now if now is not None else datetime.now(tz=timezone.utc)
    metadata = chunk.metadata
    if chunk.source == "gmail":
        sent_at = metadata.get("sent_at", "")
        return (
            f"Gmail email from {metadata.get('sender', '')}, "
            f"sent {sent_at}{_relative_days_label(sent_at, now)}, "
            f"subject: '{metadata.get('subject', '')}'"
        )
    if chunk.source == "calendar":
        start_at = metadata.get("start_at", "")
        return (
            f"Calendar event '{metadata.get('summary', '')}' "
            f"starting {start_at}{_relative_days_label(start_at, now)}"
        )
    if chunk.source == "docs":
        return f"Google Doc titled '{metadata.get('title', '')}'"
    if chunk.source == "local_files":
        return f"Note file at {metadata.get('path', '')}"
    return f"{chunk.source} item {chunk.source_item_id}"


def build_user_message(question: str, chunks: list[RetrievedChunk], *, now: datetime | None = None) -> str:
    """assembles the question plus every retrieved chunk's parent context
    into one message, numbered for citation. this whole string gets
    tokenized exactly once before being sent externally. `now` drives the
    per-item "(N days ago)" / "(in N days)" labels in _source_label, so the
    model never has to compute past-vs-future itself."""
    now = now if now is not None else datetime.now(tz=timezone.utc)
    lines = [f"Today's date: {now.date().isoformat()}", "", f"Question:\n{question}", "", "Context:"]
    for index, chunk in enumerate(chunks, start=1):
        lines.append(f"[{index}] {_source_label(chunk, now=now)}")
        lines.append(chunk.parent_text)
        lines.append("")
    return "\n".join(lines).strip()


def format_sources(chunks: list[RetrievedChunk], *, now: datetime | None = None) -> str:
    """renders the final source list from data this project already owns -
    not parsed out of claude's response, which only produces the inline
    [N] citation markers in its prose."""
    now = now if now is not None else datetime.now(tz=timezone.utc)
    lines = ["Sources:"]
    for index, chunk in enumerate(chunks, start=1):
        lines.append(f"[{index}] {_source_label(chunk, now=now)}")
    return "\n".join(lines)
