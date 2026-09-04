from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from langgraph.types import Command

from meridian.digest.graph import build_digest_graph
from meridian.digest.store import DigestStore

RunStatus = Literal["skipped_pending", "nothing_new", "awaiting_review"]
ReviewStatus = Literal["not_found", "already_decided", "approved", "rejected"]


@dataclass(frozen=True)
class RunDigestResult:
    status: RunStatus
    run_id: str | None
    digest_text: str | None = None
    sources_text: str | None = None


@dataclass(frozen=True)
class ReviewResult:
    status: ReviewStatus
    run_id: str


def run_digest_job(
    *,
    digest_store: DigestStore,
    gmail_store: Any,
    calendar_store: Any,
    docs_store: Any,
    notes_store: Any,
    entity_store: Any,
    analyzer: Any,
    client: Any,
    model: str,
    checkpointer: Any,
    lookback: timedelta = timedelta(hours=24),
    lookahead: timedelta = timedelta(days=3),
    now: datetime | None = None,
    logger: logging.Logger | None = None,
) -> RunDigestResult:
    """generates a new digest awaiting review, unless one is already
    pending - refusing to start a second run avoids duplicate/overlapping
    LLM-generated digests piling up before the user reviews the first."""
    now = now or datetime.now(timezone.utc)

    pending = digest_store.get_pending_run()
    if pending is not None:
        return RunDigestResult(status="skipped_pending", run_id=pending["run_id"])

    cursor = digest_store.get_cursor()
    window_start = cursor or (now - lookback).isoformat()
    window_end = now.isoformat()
    lookahead_end = (now + lookahead).isoformat()

    run_id = str(uuid4())
    graph = build_digest_graph(
        gmail_store, calendar_store, docs_store, notes_store, entity_store,
        analyzer, client, model, checkpointer, now=now, logger=logger,
    )
    config = {"configurable": {"thread_id": run_id}}
    result = graph.invoke(
        {"window_start": window_start, "window_end": window_end, "lookahead_end": lookahead_end},
        config=config,
    )

    if "__interrupt__" in result:
        digest_store.create_run(
            run_id, window_start, window_end,
            result["digest_text"], result["sources_text"],
            len(result["items"]), result["llm_used"],
        )
        return RunDigestResult(
            status="awaiting_review", run_id=run_id,
            digest_text=result["digest_text"], sources_text=result["sources_text"],
        )

    # the nothing_new path completed straight through to END with no
    # interrupt - no approval needed for an empty digest, so the cursor
    # advances immediately.
    digest_store.set_cursor(window_end)
    return RunDigestResult(status="nothing_new", run_id=None)


def review_digest_job(
    *,
    digest_store: DigestStore,
    gmail_store: Any,
    calendar_store: Any,
    docs_store: Any,
    notes_store: Any,
    entity_store: Any,
    analyzer: Any,
    client: Any,
    model: str,
    checkpointer: Any,
    run_id: str,
    approve: bool,
    logger: logging.Logger | None = None,
) -> ReviewResult:
    run = digest_store.get_run(run_id)
    if run is None:
        return ReviewResult(status="not_found", run_id=run_id)
    if run["status"] != "pending":
        return ReviewResult(status="already_decided", run_id=run_id)

    graph = build_digest_graph(
        gmail_store, calendar_store, docs_store, notes_store, entity_store,
        analyzer, client, model, checkpointer, logger=logger,
    )
    config = {"configurable": {"thread_id": run_id}}
    graph.invoke(Command(resume=approve), config=config)

    if approve:
        digest_store.mark_approved(run_id)
        status: ReviewStatus = "approved"
    else:
        digest_store.mark_rejected(run_id)
        status = "rejected"

    # advances on either decision - there's no "regenerate" flow, and
    # re-covering the same window after a rejection would just waste
    # another LLM call on similar content. run_digest_job refuses to start
    # a second run while one is pending, so the run being reviewed here is
    # always the only pending one - no ambiguity about whose window this is.
    digest_store.set_cursor(run["window_end"])
    return ReviewResult(status=status, run_id=run_id)
