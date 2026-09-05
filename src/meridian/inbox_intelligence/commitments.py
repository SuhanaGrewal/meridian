from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from meridian.inbox_intelligence.commitment_prompt import SYSTEM_PROMPT, build_user_message
from meridian.inbox_intelligence.deadlines import resolve_deadline_phrase
from meridian.inbox_intelligence.gmail_filters import NON_ACTIONABLE_CATEGORIES, looks_like_auto_reply
from meridian.inbox_intelligence.store import InboxIntelligenceStore
from meridian.query.anthropic_client import call_claude
from meridian.query.date_range import parse_stored_date
from meridian.redaction.tokenize import tokenize_for_external_call, untokenize
from meridian.security.audit_log import record_event

# a deterministic backstop alongside the prompt-level fix, not a
# replacement for it - LLM judgment is stochastic, this catches the
# pattern reliably every time. Boilerplate policy/SLA text almost always
# describes a *recurring turnaround window* ("within 2 hours," "during
# business hours," "typically respond within 24 hours") rather than a
# deadline tied to this specific exchange - a real commitment says "by
# Friday" or "tomorrow," not "within our normal business hours."
_BOILERPLATE_POLICY_RE = re.compile(
    r"\b(business hours|operational hours|office hours|"
    r"standard (response|policy|turnaround)|typical(ly)? respond|"
    r"we aim to respond|responds? within|response time|"
    r"(support|customer service) team (typically|usually|generally))\b",
    re.IGNORECASE,
)


def _looks_like_boilerplate_policy(description: str, deadline_phrase: str | None) -> bool:
    combined = f"{description} {deadline_phrase or ''}"
    return bool(_BOILERPLATE_POLICY_RE.search(combined))


@dataclass(frozen=True)
class ScanStats:
    messages_scanned: int
    commitments_found: int


def _parse_extraction_response(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().upper()] = value.strip()
    return fields


def _first_recipient(recipients_json: str | None) -> str:
    if not recipients_json:
        return ""
    try:
        recipients = json.loads(recipients_json)
    except (ValueError, TypeError):
        return ""
    return recipients[0] if recipients else ""


def _eligible_messages(gmail_store: Any, commitment_store: InboxIntelligenceStore, limit: int) -> list[Any]:
    """most-recent-first, skipping already-scanned and non-conversational
    mail (promo/social/updates/forums categories, auto-replies) - no point
    spending an LLM call on a newsletter that will never contain a
    commitment."""
    all_messages = sorted(gmail_store.get_all_messages(), key=lambda row: row["sent_at"] or "", reverse=True)
    eligible = []
    for row in all_messages:
        if len(eligible) >= limit:
            break
        if commitment_store.is_message_scanned(row["message_id"]):
            continue
        labels = set(json.loads(row["label_ids"] or "[]"))
        if labels & NON_ACTIONABLE_CATEGORIES:
            continue
        if looks_like_auto_reply(row["subject"], row["sender"]):
            continue
        eligible.append(row)
    return eligible


def scan_for_commitments(
    gmail_store: Any,
    commitment_store: InboxIntelligenceStore,
    account_email: str,
    client: Any,
    model: str,
    analyzer: Any,
    *,
    limit: int = 50,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> ScanStats:
    """scans up to `limit` not-yet-scanned, conversational messages
    (newest first) for a soft commitment, one Claude call per message.
    Redacts before every call and records an audit event, same as
    query/answer.py. The LLM extracts the commitment description and the
    raw deadline phrase only - deadlines.resolve_deadline_phrase() does
    the actual date arithmetic in code, anchored to the message's real
    sent_at, since asking an LLM to also do that arithmetic is unreliable
    (see query/prompt.py's _relative_days_label for the same lesson)."""
    account_email_lower = account_email.strip().lower()
    messages = _eligible_messages(gmail_store, commitment_store, limit)
    commitments_found = 0

    for row in messages:
        user_message_text = build_user_message(
            sender=row["sender"] or "",
            subject=row["subject"] or "",
            sent_at=row["sent_at"] or "",
            body_text=row["body_text"] or "",
        )
        tokenization = tokenize_for_external_call(user_message_text, analyzer=analyzer, logger=logger)
        if audit_log_dir is not None:
            record_event(
                audit_log_dir,
                "llm.external_call",
                {
                    "operation": "inbox_intelligence.commitment_scan",
                    "entity_counts": tokenization.entity_counts,
                },
            )
        raw_response = call_claude(
            client, model=model, system=SYSTEM_PROMPT, user_message=tokenization.tokenized_text, logger=logger
        )
        response = untokenize(raw_response, tokenization.mapping)
        fields = _parse_extraction_response(response)

        commitment_store.mark_message_scanned(row["message_id"])

        if fields.get("HAS_COMMITMENT", "").lower() != "yes":
            continue

        description = fields.get("DESCRIPTION", "").strip()
        if not description:
            continue

        deadline_phrase = fields.get("DEADLINE_PHRASE", "").strip()
        if deadline_phrase.upper() in ("", "NONE"):
            deadline_phrase = None

        if _looks_like_boilerplate_policy(description, deadline_phrase):
            continue

        _, sender_email = parseaddr(row["sender"] or "")
        is_from_me = sender_email.lower() == account_email_lower
        made_by = "me" if is_from_me else "other"
        other_party = _first_recipient(row["recipients"]) if is_from_me else (row["sender"] or "")

        sent_at = parse_stored_date(row["sent_at"])
        due_date = None
        if sent_at is not None:
            resolved = resolve_deadline_phrase(deadline_phrase, sent_at.date())
            due_date = resolved.isoformat() if resolved is not None else None

        commitment_store.add_commitment(
            message_id=row["message_id"],
            thread_id=row["thread_id"],
            made_by=made_by,
            other_party=other_party,
            description=description,
            deadline_phrase=deadline_phrase,
            due_date=due_date,
        )
        commitments_found += 1

    if logger is not None:
        logger.info(
            "commitment scan complete",
            extra={
                "operation": "inbox_intelligence.commitment_scan",
                "status": "success",
                "duration_ms": 0,
                "messages_scanned": len(messages),
                "commitments_found": commitments_found,
            },
        )

    return ScanStats(messages_scanned=len(messages), commitments_found=commitments_found)
