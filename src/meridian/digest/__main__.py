from __future__ import annotations

import argparse
import functools
import sqlite3
from datetime import timedelta

from langgraph.checkpoint.sqlite import SqliteSaver

from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger
from meridian.digest.orchestrator import review_digest_job, run_digest_job
from meridian.digest.store import DigestStore
from meridian.entity_graph.store import EntityGraphStore
from meridian.indexing.embedder import build_embedder
from meridian.indexing.store import IndexStore
from meridian.ingestion.calendar.store import CalendarStore
from meridian.ingestion.docs.store import DocsStore
from meridian.ingestion.gmail.store import GmailStore
from meridian.ingestion.local_files.store import NotesStore
from meridian.query.anthropic_client import build_client
from meridian.query.answer import ask
from meridian.query.history_store import QueryHistoryStore
from meridian.query.reranker import build_reranker
from meridian.redaction.analyzer import build_analyzer_engine
from meridian.security.field_encryption import derive_or_load_key


def _build_stores(config):
    encryption_key = derive_or_load_key(config.security_dir)
    return {
        "digest_store": DigestStore(config.digest_dir / "digest.db", encryption_key=encryption_key),
        "gmail_store": GmailStore(config.ingestion_dir / "gmail" / "gmail.db"),
        "calendar_store": CalendarStore(config.ingestion_dir / "calendar" / "calendar.db"),
        "docs_store": DocsStore(config.ingestion_dir / "docs" / "docs.db"),
        "notes_store": NotesStore(config.ingestion_dir / "local_files" / "local_files.db"),
        "entity_store": EntityGraphStore(config.entity_graph_dir / "entity_graph.db"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and review Meridian's periodic digest."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Gather what's new and generate a digest awaiting review."
    )
    run_parser.add_argument(
        "--lookback-hours", type=float, default=24.0,
        help="Hours to look back before any review cursor exists (default: 24).",
    )
    run_parser.add_argument(
        "--lookahead-days", type=float, default=3.0,
        help="Days to look ahead for upcoming calendar events (default: 3).",
    )
    run_parser.add_argument(
        "--model", default=None,
        help="Override the Claude model to use (default: from .env's LLM_MODEL).",
    )

    review_parser = subparsers.add_parser(
        "review", help="List pending digests, or approve/reject one."
    )
    group = review_parser.add_mutually_exclusive_group()
    group.add_argument("--approve", metavar="RUN_ID", help="Approve the given pending run.")
    group.add_argument("--reject", metavar="RUN_ID", help="Reject the given pending run.")

    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.digest.cli", log_dir=config.log_dir)

    stores = _build_stores(config)
    checkpointer = SqliteSaver(
        sqlite3.connect(config.digest_dir / "checkpoints.db", check_same_thread=False)
    )
    analyzer = build_analyzer_engine()
    client = build_client(config.llm_api_key) if config.llm_api_key else None
    if client is None:
        print("LLM_API_KEY is not set - the digest will be a plain listing, not an LLM summary.\n")

    if args.command == "run":
        model = args.model or config.llm_model
        history_store = None
        ask_fn = None
        if client is not None:
            # follow-up tracking (#9) reuses the exact same grounded
            # retrieval pipeline a direct query would use - no separate
            # "is this resolved" retrieval logic - just bound to a fixed
            # question-less signature so digest/graph.py can call it plainly.
            history_store = QueryHistoryStore(config.query_dir / "query_history.db")
            index_store = IndexStore(config.indexing_dir / "index.db")
            embedder = build_embedder()
            reranker = build_reranker()
            ask_fn = functools.partial(
                ask, store=index_store, embedder=embedder, reranker=reranker, analyzer=analyzer,
                client=client, model=model, logger=logger, audit_log_dir=config.log_dir,
            )

        result = run_digest_job(
            **stores,
            analyzer=analyzer,
            client=client,
            model=model,
            checkpointer=checkpointer,
            history_store=history_store,
            ask_fn=ask_fn,
            lookback=timedelta(hours=args.lookback_hours),
            lookahead=timedelta(days=args.lookahead_days),
            logger=logger,
            audit_log_dir=config.log_dir,
        )
        if result.status == "skipped_pending":
            print(f"A digest is already pending review (run_id={result.run_id}). Run `review` first.")
        elif result.status == "nothing_new":
            print("Nothing new to digest.")
        else:
            print(f"Digest awaiting review (run_id={result.run_id}):\n")
            print(result.digest_text)
            print()
            print(result.sources_text)
        return

    # review
    if not args.approve and not args.reject:
        pending = stores["digest_store"].list_pending_runs()
        if not pending:
            print("No digests awaiting review.")
            return
        for run in pending:
            print(f"run_id={run['run_id']}  window={run['window_start']} to {run['window_end']}  items={run['item_count']}\n")
            print(run["digest_text"])
            print()
            print(run["sources_text"])
            print("\n---\n")
        return

    # model is unused on this path - resuming a paused graph re-enters
    # only the review node, never summarize, so no LLM call happens here.
    run_id = args.approve or args.reject
    result = review_digest_job(
        **stores,
        analyzer=analyzer,
        client=client,
        model=config.llm_model,
        checkpointer=checkpointer,
        run_id=run_id,
        approve=bool(args.approve),
        logger=logger,
        audit_log_dir=config.log_dir,
    )
    print(f"{run_id}: {result.status}")


if __name__ == "__main__":
    main()
