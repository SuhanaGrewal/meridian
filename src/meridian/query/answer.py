from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from meridian.indexing.embedder import embed_chunks
from meridian.indexing.store import IndexStore
from meridian.query.anthropic_client import call_claude
from meridian.query.date_range import extract_date_range
from meridian.query.prompt import SYSTEM_PROMPT, build_user_message, format_sources
from meridian.query.retrieval import AbstainReason, RetrievedChunk, retrieve
from meridian.redaction.tokenize import tokenize_for_external_call, untokenize
from meridian.security.audit_log import record_event


@dataclass(frozen=True)
class AnswerResult:
    question: str
    chunks: list[RetrievedChunk]
    confidence: float
    abstained: bool
    abstain_reason: AbstainReason | None
    answer: str | None
    sources: str | None
    llm_configured: bool


def ask(
    question: str,
    *,
    store: IndexStore,
    embedder: Any,
    reranker: Any,
    analyzer: Any,
    client: Any,
    model: str,
    source: str | None = None,
    now: datetime | None = None,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> AnswerResult:
    """runs the full query pipeline: retrieve, then either abstain, report
    retrieval-only results (no api key configured), or generate a grounded
    answer.

    the redaction mapping is a local variable here, built by exactly one
    tokenize_for_external_call() covering the whole prompt and consumed by
    exactly one untokenize() on the response - it never outlives this call
    and is never persisted, per the project's redaction design."""
    now = now if now is not None else datetime.now(tz=timezone.utc)
    date_range = extract_date_range(question, now=now)

    question_embedding = np.array(embed_chunks(embedder, [question])[0], dtype=np.float32)

    result = retrieve(
        store,
        question,
        question_embedding,
        reranker=reranker,
        date_range=date_range,
        source=source,
        logger=logger,
    )

    if result.abstained:
        return AnswerResult(
            question=question,
            chunks=result.chunks,
            confidence=result.confidence,
            abstained=True,
            abstain_reason=result.abstain_reason,
            answer=None,
            sources=None,
            llm_configured=client is not None,
        )

    if client is None:
        return AnswerResult(
            question=question,
            chunks=result.chunks,
            confidence=result.confidence,
            abstained=False,
            abstain_reason=None,
            answer=None,
            sources=None,
            llm_configured=False,
        )

    user_message = build_user_message(question, result.chunks)
    tokenization = tokenize_for_external_call(user_message, analyzer=analyzer, logger=logger)
    if audit_log_dir is not None:
        record_event(
            audit_log_dir, "llm.external_call",
            {"operation": "query.ask", "entity_counts": tokenization.entity_counts},
        )
    raw_answer = call_claude(
        client,
        model=model,
        system=SYSTEM_PROMPT,
        user_message=tokenization.tokenized_text,
        logger=logger,
    )
    answer = untokenize(raw_answer, tokenization.mapping)

    return AnswerResult(
        question=question,
        chunks=result.chunks,
        confidence=result.confidence,
        abstained=False,
        abstain_reason=None,
        answer=answer,
        sources=format_sources(result.chunks),
        llm_configured=True,
    )
