from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from meridian.indexing.embedder import embed_chunks
from meridian.indexing.store import IndexStore
from meridian.query.anthropic_client import call_claude
from meridian.query.date_range import extract_date_range, is_forward_looking_range
from meridian.query.prompt import (
    SYSTEM_PROMPT,
    TIEBREAK_SYSTEM_PROMPT,
    build_tiebreak_user_message,
    build_user_message,
    format_sources,
)
from meridian.query.retrieval import AbstainReason, RetrievedChunk, retrieve
from meridian.redaction.tokenize import tokenize_for_external_call, untokenize
from meridian.security.audit_log import record_event


def _llm_confirms_relevance(
    question: str, candidate_text: str, *, client: Any, model: str, analyzer: Any,
    logger: logging.Logger | None = None, audit_log_dir: Path | None = None,
) -> bool:
    """a last-resort check before abstaining: the local cross-encoder
    reranker (a small MiniLM model) occasionally scores a genuinely
    correct top candidate too low to trust - confirmed via real testing
    on typo-laden or vocabulary-mismatched questions where the actual
    answer existed but the reranker's score was nowhere near the abstain
    threshold. Rather than adding a second, heavier reranker model (which
    would likely share the same blind spot - it's a vocabulary-matching
    limitation, not a model-size one), this reuses Claude itself, the same
    "ask the LLM to judge instead of guessing" pattern already used
    throughout this project (commitment filtering, resolve-matching,
    reminder-matching). Only spent on the already-rare abstaining path, so
    cost stays bounded to queries that would otherwise get nothing."""
    user_message = build_tiebreak_user_message(question, candidate_text)
    tokenization = tokenize_for_external_call(user_message, analyzer=analyzer, logger=logger)
    if audit_log_dir is not None:
        record_event(
            audit_log_dir, "llm.external_call",
            {"operation": "query.rerank_tiebreak", "entity_counts": tokenization.entity_counts},
        )
    raw = call_claude(
        client, model=model, system=TIEBREAK_SYSTEM_PROMPT, user_message=tokenization.tokenized_text,
        max_tokens=10, logger=logger,
    )
    return "YES" in raw.strip().upper()


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

    if result.abstained and date_range is not None and is_forward_looking_range(date_range, now=now):
        # nothing upcoming matched confidently - fall back to an
        # unfiltered search so a real past match (if one exists) can
        # still surface for context ("no upcoming flights, but here's
        # your last one") instead of just abstaining. Triggered on ANY
        # abstain reason, not just "no_candidates_in_date_range": docs/
        # local_files chunks have no date concept and always pass the
        # date filter (chunk_in_range's documented fail-open behavior),
        # so a date-filtered search with irrelevant docs still in the
        # pool typically abstains as "low_confidence" instead - the date
        # filter narrowed the pool without ever emptying it outright.
        # Removing the filter can only surface more candidates, never
        # fewer, so retrying is always safe here. SYSTEM_PROMPT already
        # knows how to frame "nothing upcoming, here's the most recent
        # past item" correctly via per-item recency labels - the filter
        # was just preventing it from ever seeing a real candidate to
        # frame that way.
        fallback = retrieve(
            store, question, question_embedding, reranker=reranker, date_range=None, source=source, logger=logger,
        )
        result = fallback if not fallback.abstained else replace(fallback, abstain_reason="no_upcoming_match")

    if result.abstained and result.chunks and client is not None:
        # result.chunks is non-empty here only for a score-based abstain
        # (low_confidence / no_upcoming_match) - "no_candidates" and
        # "no_candidates_in_date_range" return an empty chunk list, so
        # there's nothing to tiebreak and this is skipped for those.
        top_chunk = result.chunks[0]
        if _llm_confirms_relevance(
            question, top_chunk.parent_text, client=client, model=model, analyzer=analyzer,
            logger=logger, audit_log_dir=audit_log_dir,
        ):
            result = replace(result, abstained=False, abstain_reason=None, chunks=[top_chunk])

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

    user_message = build_user_message(question, result.chunks, now=now)
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
        sources=format_sources(result.chunks, now=now),
        llm_configured=True,
    )
