from __future__ import annotations

import argparse

from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger
from meridian.indexing.embedder import build_embedder
from meridian.indexing.orchestrator import run_indexing
from meridian.indexing.store import IndexStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index ingested content for hybrid vector + keyword search."
    )
    parser.add_argument(
        "--source",
        choices=["gmail", "calendar", "docs", "local_files"],
        action="append",
        help="Limit indexing to one source (repeatable). Defaults to all four.",
    )
    parser.add_argument(
        "--full-reindex",
        action="store_true",
        help="Reprocess every item regardless of whether it changed since the last run.",
    )
    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.indexing.cli", log_dir=config.log_dir)

    store = IndexStore(config.indexing_dir / "index.db")
    embedder = build_embedder()

    results = run_indexing(
        config.ingestion_dir,
        store,
        embedder,
        sources=args.source,
        force=args.full_reindex,
        logger=logger,
    )

    for source, stats in results.items():
        print(
            f"{source}: {stats.items_indexed} indexed, {stats.items_skipped_unchanged} unchanged, "
            f"{stats.items_deleted} deleted, {stats.chunks_written} chunks written "
            f"in {stats.duration_ms:.0f}ms."
        )


if __name__ == "__main__":
    main()
