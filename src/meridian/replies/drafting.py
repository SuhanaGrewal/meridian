from __future__ import annotations

import logging
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from meridian.query.anthropic_client import call_claude
from meridian.redaction.tokenize import tokenize_for_external_call, untokenize
from meridian.replies.draft_prompt import DRAFT_REPLY_SYSTEM_PROMPT, build_draft_user_message
from meridian.replies.relationship import classify_relationship
from meridian.replies.store import DraftStore
from meridian.replies.voice import sample_voice_examples
from meridian.security.audit_log import record_event

_DRAFT_MAX_TOKENS = 800


class MessageNotFoundError(Exception):
    pass


def draft_reply_for_message(
    gmail_store: Any,
    draft_store: DraftStore,
    account_email: str,
    message_id: str,
    *,
    client: Any,
    model: str,
    analyzer: Any,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> str:
    """drafts a reply to one specific message, in the user's own voice
    (recent sent-mail excerpts as style examples - see replies/voice.py)
    and adjusted by relationship to the sender (replies/relationship.py),
    then stores it via DraftStore. This is drafting only - there is no
    send path here or anywhere else in this project; storing the draft as
    'pending' is the entire output. Raises MessageNotFoundError for an
    unknown message_id rather than silently drafting nothing."""
    row = gmail_store.get_message_row(message_id)
    if row is None:
        raise MessageNotFoundError(message_id)

    _, recipient_email = parseaddr(row["sender"] or "")
    recipient_email = recipient_email.lower() or None

    voice_examples = sample_voice_examples(gmail_store, account_email)
    relationship = (
        classify_relationship(gmail_store, recipient_email, exclude_message_id=message_id)
        if recipient_email
        else "new"
    )

    user_message = build_draft_user_message(
        sender=row["sender"] or "",
        subject=row["subject"] or "",
        sent_at=row["sent_at"] or "",
        body_text=row["body_text"] or "",
        voice_examples=voice_examples,
        relationship=relationship,
    )

    tokenization = tokenize_for_external_call(user_message, analyzer=analyzer, logger=logger)
    if audit_log_dir is not None:
        record_event(
            audit_log_dir, "llm.external_call",
            {"operation": "replies.draft", "entity_counts": tokenization.entity_counts},
        )
    raw = call_claude(
        client, model=model, system=DRAFT_REPLY_SYSTEM_PROMPT, user_message=tokenization.tokenized_text,
        max_tokens=_DRAFT_MAX_TOKENS, logger=logger,
    )
    draft_text = untokenize(raw, tokenization.mapping)

    return draft_store.add_draft(row["thread_id"], message_id, recipient_email, draft_text)
