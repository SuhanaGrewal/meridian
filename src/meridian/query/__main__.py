from __future__ import annotations

import argparse

from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger
from meridian.inbox_intelligence.store import InboxIntelligenceStore
from meridian.indexing.embedder import build_embedder
from meridian.indexing.store import IndexStore
from meridian.ingestion.gmail.store import GmailStore
from meridian.query.anthropic_client import build_client
from meridian.query.answer import ask
from meridian.query.reranker import build_reranker
from meridian.query.router import route
from meridian.redaction.analyzer import build_analyzer_engine

_ABSTAIN_MESSAGES = {
    "no_candidates": "Nothing in the index looks related to that question.",
    "no_candidates_in_date_range": "Found related content, but none of it falls in that date range.",
    "low_confidence": "Nothing found was a confident enough match to answer from.",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask a question over Meridian's indexed content."
    )
    parser.add_argument("question", help="question to ask (wrap in quotes)")
    parser.add_argument(
        "--source",
        choices=["gmail", "calendar", "docs", "local_files"],
        help="Limit retrieval to one source. Defaults to searching all indexed sources.",
    )
    parser.add_argument(
        "--top-k", type=int, default=5, help="Number of context chunks to retrieve (default: 5)."
    )
    parser.add_argument(
        "--model", default=None, help="Override the Claude model to use (default: from .env's LLM_MODEL)."
    )
    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.query.cli", log_dir=config.log_dir)

    store = IndexStore(config.indexing_dir / "index.db")
    embedder = build_embedder()
    reranker = build_reranker()
    analyzer = build_analyzer_engine()

    client = build_client(config.llm_api_key) if config.llm_api_key else None
    if client is None:
        print("LLM_API_KEY is not set - showing retrieved context only, no answer will be generated.\n")

    if client is not None:
        # routing (stale threads / commitments / resolve / general) needs a
        # real LLM call just to classify the message - with no client,
        # skip straight to retrieval-only ask() below, same as always.
        gmail_store = GmailStore(config.ingestion_dir / "gmail" / "gmail.db")
        inbox_store = InboxIntelligenceStore(config.inbox_intelligence_dir / "commitments.db")
        router_result = route(
            args.question,
            gmail_store=gmail_store,
            inbox_store=inbox_store,
            account_email=gmail_store.get_account_email(),
            client=client,
            model=args.model or config.llm_model,
            analyzer=analyzer,
            logger=logger,
            audit_log_dir=config.log_dir,
        )
        if router_result.answer is not None:
            print(router_result.answer)
            return

    result = ask(
        args.question,
        store=store,
        embedder=embedder,
        reranker=reranker,
        analyzer=analyzer,
        client=client,
        model=args.model or config.llm_model,
        source=args.source,
        logger=logger,
        audit_log_dir=config.log_dir,
    )

    if result.abstained:
        print(_ABSTAIN_MESSAGES[result.abstain_reason])
        return

    if result.answer is not None:
        print(result.answer)
        print()
        print(result.sources)
        return

    print(f"Retrieval-only results (confidence: {result.confidence:.2f}):\n")
    for index, chunk in enumerate(result.chunks, start=1):
        print(f"[{index}] ({chunk.source}, confidence {chunk.confidence:.2f})")
        print(chunk.parent_text)
        print()
    print("LLM not configured - set LLM_API_KEY to enable answer generation.")


if __name__ == "__main__":
    main()
