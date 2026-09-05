from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from meridian.digest.gather import gather_items
from meridian.inbox_intelligence.stale_threads import find_stale_threads
from meridian.query.anthropic_client import call_claude
from meridian.query.date_range import extract_date_range
from meridian.query.router_prompt import (
    CLASSIFY_SYSTEM_PROMPT,
    MATCH_DRAFT_TARGET_SYSTEM_PROMPT,
    MATCH_RESOLVE_SYSTEM_PROMPT,
    SUMMARIZE_BROAD_ASK_SYSTEM_PROMPT,
    SUMMARIZE_STALE_THREADS_SYSTEM_PROMPT,
    build_broad_ask_user_message,
    build_draft_target_candidates_message,
    build_resolve_candidates_message,
    build_stale_threads_user_message,
)
from meridian.redaction.tokenize import tokenize_for_external_call, untokenize
from meridian.reminders.scheduling import propose_free_slot
from meridian.replies.drafting import MessageNotFoundError, draft_reply_for_message
from meridian.security.audit_log import record_event

Intent = Literal[
    "stale_threads", "commitments", "resolve", "broad_summary", "reminder", "draft_reply", "general"
]

# default backward-looking window for a broad ask with no recognized date
# phrase of its own (e.g. "summarize my recent emails") - matches
# digest's own --lookback-hours-ish philosophy of "a sensible recent
# window," not an exhaustive all-time gather.
_DEFAULT_BROAD_ASK_LOOKBACK_DAYS = 7
_DEFAULT_BROAD_ASK_LOOKAHEAD_DAYS = 3

# a mailbox's full history can hold hundreds of ancient "stale" threads
# (see inbox_intelligence's own real-data finding: 574 before this kind of
# cap). Routing through natural language shouldn't dump that entire
# backlog into every summarization/resolve-matching prompt - cap to a
# recent, actually-relevant window by default. This mirrors the
# stale-threads CLI's --max-days flag, just applied automatically instead
# of asked of the user.
_DEFAULT_MAX_DAYS_QUIET = 30


@dataclass(frozen=True)
class RouterResult:
    intent: Intent
    # None means: this intent wasn't (or couldn't be) handled here - the
    # caller should fall through to query.answer.ask() as usual. Keeping
    # that fallback in the caller avoids duplicating ask()'s own
    # abstain-handling and formatting here.
    answer: str | None


def _call_llm(
    *, client: Any, model: str, system: str, text: str, analyzer: Any,
    max_tokens: int = 1024, logger: logging.Logger | None = None, audit_log_dir: Path | None = None,
    operation: str,
) -> str:
    tokenization = tokenize_for_external_call(text, analyzer=analyzer, logger=logger)
    if audit_log_dir is not None:
        record_event(
            audit_log_dir, "llm.external_call",
            {"operation": operation, "entity_counts": tokenization.entity_counts},
        )
    raw = call_claude(
        client, model=model, system=system, user_message=tokenization.tokenized_text,
        max_tokens=max_tokens, logger=logger,
    )
    return untokenize(raw, tokenization.mapping)


def classify_intent(
    text: str, *, client: Any, model: str, analyzer: Any,
    logger: logging.Logger | None = None, audit_log_dir: Path | None = None,
) -> Intent:
    response = _call_llm(
        client=client, model=model, system=CLASSIFY_SYSTEM_PROMPT, text=text, analyzer=analyzer,
        max_tokens=20, logger=logger, audit_log_dir=audit_log_dir, operation="query.router_classify",
    )
    normalized = response.strip().upper()
    if "STALE_THREADS" in normalized:
        return "stale_threads"
    if "COMMITMENTS" in normalized:
        return "commitments"
    if "RESOLVE" in normalized:
        return "resolve"
    if "BROAD_SUMMARY" in normalized:
        return "broad_summary"
    if "REMINDER" in normalized:
        return "reminder"
    if "DRAFT_REPLY" in normalized:
        return "draft_reply"
    return "general"


def _summarize_stale_threads(
    text: str, threads: list[Any], *, client: Any, model: str, analyzer: Any,
    logger: logging.Logger | None = None, audit_log_dir: Path | None = None,
) -> str:
    if not threads:
        return "No threads are waiting on your reply right now."
    user_message = build_stale_threads_user_message(text, threads)
    return _call_llm(
        client=client, model=model, system=SUMMARIZE_STALE_THREADS_SYSTEM_PROMPT, text=user_message,
        analyzer=analyzer, logger=logger, audit_log_dir=audit_log_dir,
        operation="query.router_stale_threads_summary",
    )


def _format_commitments(commitments: list[Any]) -> str:
    """no LLM call needed - a commitment's description is already a short,
    LLM-distilled fact from extraction time (see
    inbox_intelligence/commitments.py), not raw email text, so it doesn't
    need re-summarizing here."""
    if not commitments:
        return "No open commitments right now."
    lines = []
    for row in commitments:
        who = "You" if row["made_by"] == "me" else row["other_party"]
        due = f" (due {row['due_date']})" if row["due_date"] else ""
        lines.append(f"{who}: {row['description']}{due}")
    return "\n".join(lines)


def _summarize_broad_ask(
    text: str,
    *,
    gmail_store: Any,
    calendar_store: Any,
    docs_store: Any,
    notes_store: Any,
    entity_store: Any,
    now: datetime,
    client: Any,
    model: str,
    analyzer: Any,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> str:
    """reuses digest/gather.py's gather_items() rather than reimplementing
    "grab everything recent" - this is exactly the same problem the
    digest already solves, just triggered by a direct question instead
    of a scheduled job. If the question itself names a recognizable
    window ("this week," "last month"), that's honored; otherwise a
    default 7-day lookback is used, same philosophy as digest's own
    lookback-hours default."""
    date_range = extract_date_range(text, now=now)
    since = date_range[0] if date_range is not None else now - timedelta(days=_DEFAULT_BROAD_ASK_LOOKBACK_DAYS)
    lookahead_end = now + timedelta(days=_DEFAULT_BROAD_ASK_LOOKAHEAD_DAYS)

    items = gather_items(
        gmail_store, calendar_store, docs_store, notes_store, entity_store,
        since=since.isoformat(), now=now.isoformat(), lookahead_end=lookahead_end.isoformat(), logger=logger,
    )
    if not items:
        return "Nothing relevant found for that."

    user_message = build_broad_ask_user_message(text, items)
    return _call_llm(
        client=client, model=model, system=SUMMARIZE_BROAD_ASK_SYSTEM_PROMPT, text=user_message,
        analyzer=analyzer, logger=logger, audit_log_dir=audit_log_dir, operation="query.router_broad_summary",
    )


def _handle_reminder(
    text: str,
    *,
    reminder_store: Any,
    calendar_store: Any,
    now: datetime,
) -> str:
    """records the reminder verbatim and, if a calendar is available,
    proposes (never books - see reminders/store.py) the first open slot
    over the next week via deterministic interval-scanning, not an LLM
    guess. calendar_store being None (no store wired up by the caller)
    still records the reminder, just without a proposed slot."""
    slot = propose_free_slot(calendar_store, now=now) if calendar_store is not None else None
    slot_start_iso = slot[0].isoformat() if slot else None
    slot_end_iso = slot[1].isoformat() if slot else None
    reminder_store.add_reminder(text, proposed_slot_start=slot_start_iso, proposed_slot_end=slot_end_iso)

    if slot is None:
        return f"Got it, I've noted this as a reminder: \"{text}\". No open calendar slot found in the next week."
    weekday = slot[0].strftime("%A")
    start_time = slot[0].strftime("%I:%M %p").lstrip("0")
    end_time = slot[1].strftime("%I:%M %p").lstrip("0")
    return (
        f"Got it, I've noted this as a reminder: \"{text}\". "
        f"Based on your calendar, you're free {weekday} {start_time} to "
        f"{end_time} - let me know if that works, nothing is booked automatically."
    )


def _latest_message_id_for_thread(gmail_store: Any, thread_id: str) -> str | None:
    for row in gmail_store.list_latest_message_per_thread():
        if row["thread_id"] == thread_id:
            return row["message_id"]
    return None


def _handle_draft_reply(
    text: str,
    threads: list[Any],
    *,
    gmail_store: Any,
    account_email: str,
    draft_store: Any,
    client: Any,
    model: str,
    analyzer: Any,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> str:
    """matches the request against threads currently awaiting a reply
    (the only threads it makes sense to draft one for) via one LLM call,
    then drafts via replies/drafting.py - the actual voice/relationship/
    LLM-call logic lives there, this only handles picking which thread.
    Drafting only - nothing is ever sent, see replies/store.py."""
    if not threads:
        return "There's nothing awaiting your reply right now to draft for."

    labels = [f"From {thread.last_sender}, subject '{thread.subject}'" for thread in threads]
    user_message = build_draft_target_candidates_message(text, labels)
    response = _call_llm(
        client=client, model=model, system=MATCH_DRAFT_TARGET_SYSTEM_PROMPT, text=user_message, analyzer=analyzer,
        max_tokens=20, logger=logger, audit_log_dir=audit_log_dir, operation="query.router_draft_match",
    )
    normalized = response.strip().upper()
    if "NONE" in normalized or not normalized.isdigit():
        return "I'm not sure which thread you mean - could you be more specific?"

    index = int(normalized) - 1
    if not (0 <= index < len(threads)):
        return "I'm not sure which thread you mean - could you be more specific?"

    thread = threads[index]
    message_id = _latest_message_id_for_thread(gmail_store, thread.thread_id)
    if message_id is None:
        return "I'm not sure which thread you mean - could you be more specific?"

    try:
        draft_id = draft_reply_for_message(
            gmail_store, draft_store, account_email, message_id,
            client=client, model=model, analyzer=analyzer, logger=logger, audit_log_dir=audit_log_dir,
        )
    except MessageNotFoundError:
        return "I'm not sure which thread you mean - could you be more specific?"

    draft = draft_store.get_draft(draft_id)
    return (
        f"Here's a draft reply to {thread.last_sender} (draft id: {draft_id}, nothing sent):\n\n"
        f"{draft['draft_text']}"
    )


@dataclass(frozen=True)
class _ResolvableItem:
    kind: Literal["thread", "commitment", "reminder"]
    item_id: str
    label: str


def _resolve_matching_item(
    text: str, threads: list[Any], commitments: list[Any], reminders: list[Any], inbox_store: Any, reminder_store: Any,
    *, client: Any, model: str, analyzer: Any,
    logger: logging.Logger | None = None, audit_log_dir: Path | None = None,
) -> str:
    candidates: list[_ResolvableItem] = [
        _ResolvableItem(kind="thread", item_id=thread.thread_id, label=f"Thread from {thread.last_sender}, subject '{thread.subject}'")
        for thread in threads
    ] + [
        _ResolvableItem(kind="commitment", item_id=row["commitment_id"], label=row["description"])
        for row in commitments
    ] + [
        _ResolvableItem(kind="reminder", item_id=row["reminder_id"], label=f"Reminder: {row['reminder_text']}")
        for row in reminders
    ]
    if not candidates:
        return "There's nothing open right now to mark as resolved."

    user_message = build_resolve_candidates_message(text, [item.label for item in candidates])
    response = _call_llm(
        client=client, model=model, system=MATCH_RESOLVE_SYSTEM_PROMPT, text=user_message, analyzer=analyzer,
        max_tokens=20, logger=logger, audit_log_dir=audit_log_dir, operation="query.router_resolve_match",
    )
    normalized = response.strip().upper()
    if "NONE" in normalized:
        return "I'm not sure which one you mean - could you be more specific?"

    resolved_labels = []
    for token in normalized.replace(" ", "").split(","):
        if not token.isdigit():
            continue
        index = int(token) - 1
        if not (0 <= index < len(candidates)):
            continue
        item = candidates[index]
        if item.kind == "thread":
            inbox_store.dismiss_thread(item.item_id)
        elif item.kind == "reminder":
            reminder_store.dismiss(item.item_id)
        else:
            inbox_store.mark_resolved(item.item_id)
        resolved_labels.append(item.label)

    if not resolved_labels:
        return "I'm not sure which one you mean - could you be more specific?"
    return "Marked resolved: " + "; ".join(resolved_labels)


def route(
    text: str,
    *,
    gmail_store: Any,
    inbox_store: Any,
    account_email: str | None,
    client: Any,
    model: str,
    analyzer: Any,
    calendar_store: Any = None,
    docs_store: Any = None,
    notes_store: Any = None,
    entity_store: Any = None,
    reminder_store: Any = None,
    draft_store: Any = None,
    now: datetime | None = None,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> RouterResult:
    """classifies a free-text message into stale_threads / commitments /
    resolve / broad_summary / reminder / draft_reply / general, and
    directly answers the first six (general falls through to
    query.answer.ask(), handled by the caller). This is the "everything
    is a text message" entry point - a real frontend wouldn't expose
    separate CLI subcommands per capability, it maps one text box to
    whichever backend actually answers the question. calendar_store/
    docs_store/notes_store/entity_store are only needed for
    broad_summary, reminder_store only for reminder, draft_store only for
    draft_reply - if the caller doesn't have the stores an intent needs
    wired up, that intent just falls through to general instead of
    erroring."""
    now = now if now is not None else datetime.now(tz=timezone.utc)
    intent = classify_intent(text, client=client, model=model, analyzer=analyzer, logger=logger, audit_log_dir=audit_log_dir)

    if intent == "broad_summary" and None in (calendar_store, docs_store, notes_store, entity_store):
        intent = "general"
    if intent == "reminder" and reminder_store is None:
        intent = "general"
    if intent == "draft_reply" and draft_store is None:
        intent = "general"

    if intent in ("stale_threads", "resolve", "draft_reply") and account_email is None:
        return RouterResult(
            intent=intent,
            answer="Account email not captured yet - run `python -m meridian.ingestion.gmail` first.",
        )

    if intent == "stale_threads":
        threads = find_stale_threads(
            gmail_store, account_email, now=now, max_days_quiet=_DEFAULT_MAX_DAYS_QUIET,
            exclude_thread_ids=inbox_store.list_dismissed_thread_ids(),
        )
        answer = _summarize_stale_threads(
            text, threads, client=client, model=model, analyzer=analyzer, logger=logger, audit_log_dir=audit_log_dir
        )
        return RouterResult(intent="stale_threads", answer=answer)

    if intent == "commitments":
        answer = _format_commitments(inbox_store.list_open_commitments())
        return RouterResult(intent="commitments", answer=answer)

    if intent == "resolve":
        threads = find_stale_threads(
            gmail_store, account_email, now=now, max_days_quiet=_DEFAULT_MAX_DAYS_QUIET,
            exclude_thread_ids=inbox_store.list_dismissed_thread_ids(),
        )
        commitments = inbox_store.list_open_commitments()
        reminders = reminder_store.list_pending_reminders() if reminder_store is not None else []
        answer = _resolve_matching_item(
            text, threads, commitments, reminders, inbox_store, reminder_store,
            client=client, model=model, analyzer=analyzer, logger=logger, audit_log_dir=audit_log_dir,
        )
        return RouterResult(intent="resolve", answer=answer)

    if intent == "reminder":
        answer = _handle_reminder(text, reminder_store=reminder_store, calendar_store=calendar_store, now=now)
        return RouterResult(intent="reminder", answer=answer)

    if intent == "broad_summary":
        answer = _summarize_broad_ask(
            text, gmail_store=gmail_store, calendar_store=calendar_store, docs_store=docs_store,
            notes_store=notes_store, entity_store=entity_store, now=now,
            client=client, model=model, analyzer=analyzer, logger=logger, audit_log_dir=audit_log_dir,
        )
        return RouterResult(intent="broad_summary", answer=answer)

    if intent == "draft_reply":
        threads = find_stale_threads(
            gmail_store, account_email, now=now, max_days_quiet=_DEFAULT_MAX_DAYS_QUIET,
            exclude_thread_ids=inbox_store.list_dismissed_thread_ids(),
        )
        answer = _handle_draft_reply(
            text, threads, gmail_store=gmail_store, account_email=account_email, draft_store=draft_store,
            client=client, model=model, analyzer=analyzer, logger=logger, audit_log_dir=audit_log_dir,
        )
        return RouterResult(intent="draft_reply", answer=answer)

    return RouterResult(intent="general", answer=None)
