from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from meridian.digest.gather import gather_items
from meridian.digest.prompt import (
    SYSTEM_PROMPT,
    build_digest_message,
    build_plaintext_digest,
    format_sources,
)
from meridian.digest.state import DigestState
from meridian.query.anthropic_client import call_claude
from meridian.redaction.tokenize import tokenize_for_external_call, untokenize


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
    now: datetime | None = None,
    logger: logging.Logger | None = None,
) -> Any:
    """builds the digest state machine: gather -> (nothing_new | summarize
    -> review -> (approved | rejected)). real dependencies are closed over
    here rather than threaded through state, since LangGraph nodes are
    plain (state) -> dict functions with no constructor args of their own -
    the same injection pattern as build_embedder()/build_reranker()."""

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
