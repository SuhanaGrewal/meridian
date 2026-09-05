from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from meridian.query.anthropic_client import call_claude
from meridian.query.history_prompt import (
    CHECK_RESOLVED_SYSTEM_PROMPT,
    CLASSIFY_WAITING_SYSTEM_PROMPT,
    build_check_resolved_message,
)
from meridian.query.history_store import QueryHistoryStore
from meridian.redaction.tokenize import tokenize_for_external_call, untokenize
from meridian.security.audit_log import record_event


def _call_llm(
    *, client: Any, model: str, system: str, text: str, analyzer: Any,
    max_tokens: int = 20, logger: logging.Logger | None = None, audit_log_dir: Path | None = None,
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


def record_question(
    question_text: str,
    history_store: QueryHistoryStore,
    *,
    client: Any,
    model: str,
    analyzer: Any,
    now: datetime | None = None,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> str:
    """classifies whether this question is asking about something the user
    is waiting on (vs. a plain fact lookup) and records it either way, so
    a full history exists even though only "waiting" questions ever
    surface as an open follow-up (see check_open_questions below)."""
    response = _call_llm(
        client=client, model=model, system=CLASSIFY_WAITING_SYSTEM_PROMPT, text=question_text, analyzer=analyzer,
        logger=logger, audit_log_dir=audit_log_dir, operation="query.history_classify",
    )
    is_waiting = "YES" in response.strip().upper()
    asked_at = (now if now is not None else datetime.now(tz=timezone.utc)).isoformat()
    return history_store.add_question(question_text, is_waiting=is_waiting, asked_at=asked_at)


def check_open_questions(
    history_store: QueryHistoryStore,
    *,
    ask_fn: Callable[[str], Any],
    client: Any,
    model: str,
    analyzer: Any,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> list[dict]:
    """re-asks every open "waiting" question against the current index via
    ask_fn (query.answer.ask, or an equivalent) - no separate retrieval
    logic here, this reuses the same grounded pipeline a direct question
    would use. A fresh non-abstained answer is then judged (one more small
    LLM call) for whether it actually indicates the awaited thing has now
    happened: RESOLVED marks the question resolved immediately and
    silently (a digest reports what's new/pending, not closure
    confirmations); anything else - an abstain, or a judged-PENDING answer
    - is returned so the caller can surface it as a still-open follow-up,
    per the project's design of calling out something the user is
    genuinely waiting on rather than letting it quietly age out."""
    still_open: list[dict] = []
    for row in history_store.list_open_waiting_questions():
        result = ask_fn(row["question_text"])
        if result.abstained or not result.answer:
            still_open.append({"question_text": row["question_text"], "asked_at": row["asked_at"]})
            continue

        verdict = _call_llm(
            client=client, model=model, system=CHECK_RESOLVED_SYSTEM_PROMPT,
            text=build_check_resolved_message(row["question_text"], result.answer), analyzer=analyzer,
            logger=logger, audit_log_dir=audit_log_dir, operation="query.history_check_resolved",
        )
        if "RESOLVED" in verdict.strip().upper():
            history_store.mark_resolved(row["question_id"])
        else:
            still_open.append({"question_text": row["question_text"], "asked_at": row["asked_at"]})

    return still_open
