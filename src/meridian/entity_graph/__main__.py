from __future__ import annotations

import argparse

from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger
from meridian.entity_graph.ner import build_ner_engine
from meridian.entity_graph.orchestrator import run_extraction, run_topic_pass
from meridian.entity_graph.store import EntityGraphStore
from meridian.indexing.store import IndexStore
from meridian.query.anthropic_client import build_client
from meridian.redaction.analyzer import build_analyzer_engine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract entities and link them across ingested sources."
    )
    parser.add_argument(
        "--source",
        choices=["gmail", "calendar", "docs", "local_files"],
        action="append",
        help="Limit extraction to one source (repeatable). Defaults to all four.",
    )
    parser.add_argument(
        "--full-reextract",
        action="store_true",
        help="Reprocess every item regardless of whether it changed since the last run.",
    )
    parser.add_argument(
        "--link-topics",
        action="store_true",
        help=(
            "Also link items to topic nodes for cross-thread context merging "
            "(query.router's broad_summary and future features can traverse "
            "these). Costs one real LLM call per not-yet-linked item, so this "
            "is opt-in, unlike the rest of this command which is free."
        ),
    )
    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.entity_graph.cli", log_dir=config.log_dir)

    index_store = IndexStore(config.indexing_dir / "index.db")
    entity_store = EntityGraphStore(config.entity_graph_dir / "entity_graph.db")
    nlp = build_ner_engine()

    results = run_extraction(
        config.ingestion_dir,
        index_store,
        entity_store,
        nlp,
        sources=args.source,
        force=args.full_reextract,
        logger=logger,
    )

    for source, stats in results.items():
        print(
            f"{source}: {stats.items_processed} processed, {stats.items_skipped_unchanged} unchanged, "
            f"{stats.items_deleted} deleted, {stats.mentions_recorded} mentions, "
            f"{stats.chunks_failed} failed in {stats.duration_ms:.0f}ms."
        )

    print(
        f"Entities: {entity_store.count_entities()} total "
        f"({entity_store.count_cross_source_entities()} linked across more than one source)."
    )

    if args.link_topics:
        if not config.llm_api_key:
            print("LLM_API_KEY is not set - skipping topic linking.")
        else:
            client = build_client(config.llm_api_key)
            analyzer = build_analyzer_engine()
            for source in args.source or ["gmail", "calendar", "docs", "local_files"]:
                topic_stats = run_topic_pass(
                    source, index_store, entity_store,
                    client=client, model=config.llm_model, analyzer=analyzer,
                    force=args.full_reextract, logger=logger, audit_log_dir=config.log_dir,
                )
                print(
                    f"{source} topics: {topic_stats.items_processed} linked, "
                    f"{topic_stats.items_skipped_unchanged} unchanged, "
                    f"{topic_stats.chunks_failed} failed in {topic_stats.duration_ms:.0f}ms."
                )
            print(f"Topics: {entity_store.count_topics()} total.")


if __name__ == "__main__":
    main()
