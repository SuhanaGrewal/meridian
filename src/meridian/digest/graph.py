from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from meridian.digest.gather import gather_items, open_question_item
from meridian.digest.prompt import (
    SYSTEM_PROMPT,
    build_digest_message,
    build_plaintext_digest,
    format_sources,
)
from meridian.digest.state import DigestState
from meridian.query.anthropic_client import call_claude
from meridian.query.history import check_open_questions
from meridian.redaction.tokenize import tokenize_for_external_call, untokenize
from meridian.security.audit_log import record_event


def build_digest_graph(
    gmail_store: Any,
    calendar_store: Any,
    docs_store: Any,
    notes_store: Any,
    entity_store: Any,
    analyzer: Any,
    client: Any,
    model: str,
    checkpointer: Any,
    *,
    history_store: Any = None,
    ask_fn: Any = None,
    now: datetime | None = None,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> Any:
    """builds the digest state machine: gather -> (nothing_new | summarize
    -> review -> (approved | rejected)). real dependencies are closed over
    here rather than threaded through state, since LangGraph nodes are
    plain (state) -> dict functions with no constructor args of their own -
    the same injection pattern as build_embedder()/build_reranker().

    history_store/ask_fn are optional (#9, follow-up tracking): when both
    are given, gather() also re-checks every open "waiting on something"
    question via ask_fn (query.answer.ask bound to the live index/embedder/
    reranker) and folds any still-unresolved one into the gathered items.
    Costs a real LLM call per open question, on top of the one existing
    paid call in summarize() - safe to add here specifically because
    gather() only ever executes once per run_id (a resumed/reviewed run
    re-enters at the review node's interrupt, never restarts from gather)."""

    def gather(state: DigestState) -> dict:
        window_end = state.get("window_end") or (now or datetime.now(timezone.utc)).isoformat()
        items = gather_items(
            gmail_store,
            calendar_store,
            docs_store,
            notes_store,
            entity_store,
            since=state["window_start"],
            now=window_end,
            lookahead_end=state["lookahead_end"],
            logger=logger,
        )
        if history_store is not None and ask_fn is not None and client is not None:
            open_questions = check_open_questions(
                history_store, ask_fn=ask_fn, client=client, model=model, analyzer=analyzer,
                logger=logger, audit_log_dir=audit_log_dir,
            )
            items = [open_question_item(q) for q in open_questions] + items
        return {"items": items, "window_end": window_end}

    def route_after_gather(state: DigestState) -> str:
        return "summarize" if state["items"] else "nothing_new"

    def nothing_new(state: DigestState) -> dict:
        return {"digest_text": "", "sources_text": "", "llm_used": False}

    def summarize(state: DigestState) -> dict:
        # the ONE paid/side-effecting node - review() is a separate,
        # downstream node that does nothing else, so a resume never
        # re-triggers this node's Claude call.
        if client is None:
            return {
                "digest_text": build_plaintext_digest(state["items"]),
                "sources_text": format_sources(state["items"]),
                "llm_used": False,
            }
        user_message = build_digest_message(state["window_start"], state["window_end"], state["items"])
        tokenization = tokenize_for_external_call(user_message, analyzer=analyzer, logger=logger)
        if audit_log_dir is not None:
            record_event(
                audit_log_dir, "llm.external_call",
                {"operation": "digest.summarize", "entity_counts": tokenization.entity_counts},
            )
        raw = call_claude(
            client, model=model, system=SYSTEM_PROMPT, user_message=tokenization.tokenized_text, logger=logger
        )
        return {
            "digest_text": untokenize(raw, tokenization.mapping),
            "sources_text": format_sources(state["items"]),
            "llm_used": True,
        }

    def review(state: DigestState) -> dict:
        # nothing above the interrupt() call - a resume restarts this node
        # from the top, but there's nothing here to redo.
        decision = interrupt(
            {
                "digest_text": state["digest_text"],
                "sources_text": state["sources_text"],
                "item_count": len(state["items"]),
            }
        )
        return {"decision": bool(decision)}

    def route_after_review(state: DigestState) -> str:
        return "approved" if state["decision"] else "rejected"

    def approved(state: DigestState) -> dict:
        return {}

    def rejected(state: DigestState) -> dict:
        return {}

    builder = StateGraph(DigestState)
    builder.add_node("gather", gather)
    builder.add_node("nothing_new", nothing_new)
    builder.add_node("summarize", summarize)
    builder.add_node("review", review)
    builder.add_node("approved", approved)
    builder.add_node("rejected", rejected)

    builder.add_edge(START, "gather")
    builder.add_conditional_edges(
        "gather", route_after_gather, {"summarize": "summarize", "nothing_new": "nothing_new"}
    )
    builder.add_edge("nothing_new", END)
    builder.add_edge("summarize", "review")
    builder.add_conditional_edges("review", route_after_review, {"approved": "approved", "rejected": "rejected"})
    builder.add_edge("approved", END)
    builder.add_edge("rejected", END)

    return builder.compile(checkpointer=checkpointer)
