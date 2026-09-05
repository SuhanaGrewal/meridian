from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from meridian.conversation.prompt import REWRITE_FOLLOWUP_SYSTEM_PROMPT, build_rewrite_followup_message
from meridian.query.anthropic_client import call_claude
from meridian.redaction.tokenize import tokenize_for_external_call, untokenize
from meridian.security.audit_log import record_event

_MAX_REWRITE_TOKENS = 200


def rewrite_followup_question(
    history: list[Any],
    question: str,
    *,
    client: Any,
    model: str,
    analyzer: Any,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> str:
    """expands a bare follow-up ("what about next month") into a
    standalone question using recent conversation turns. Without this,
    retrieval would embed the follow-up exactly as typed and almost
    certainly fail to find anything relevant - a bare pronoun or implicit
    reference carries no retrievable content on its own. Callers should
    skip calling this entirely when there's no history yet (an empty
    conversation has nothing to rewrite against), which this also
    enforces directly by returning the question unchanged."""
    if not history:
        return question

    user_message = build_rewrite_followup_message(history, question)
    tokenization = tokenize_for_external_call(user_message, analyzer=analyzer, logger=logger)
    if audit_log_dir is not None:
        record_event(
            audit_log_dir, "llm.external_call",
            {"operation": "query.rewrite_followup", "entity_counts": tokenization.entity_counts},
        )
    raw = call_claude(
        client, model=model, system=REWRITE_FOLLOWUP_SYSTEM_PROMPT, user_message=tokenization.tokenized_text,
        max_tokens=_MAX_REWRITE_TOKENS, logger=logger,
    )
    rewritten = untokenize(raw, tokenization.mapping).strip()
    return rewritten or question
