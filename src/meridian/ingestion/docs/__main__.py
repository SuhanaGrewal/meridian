from __future__ import annotations

import argparse
import os

from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger
from meridian.common.rate_limiter import TokenBucket
from meridian.ingestion.docs.client import build_docs_service, build_drive_service
from meridian.ingestion.docs.store import DocsStore
from meridian.ingestion.docs.sync import run_sync


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Google Docs into Meridian's local store (readonly)."
    )
    parser.add_argument(
        "--full-resync",
        action="store_true",
        help="Ignore any stored page token and re-run a full backfill from scratch.",
    )
    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.ingestion.docs.cli", log_dir=config.log_dir)

    store = DocsStore(config.ingestion_dir / "docs" / "docs.db")
    if args.full_resync:
        store.clear_sync_state()

    drive_service = build_drive_service(config=config)
    docs_service = build_docs_service(config=config)
    rate_limiter = TokenBucket(rate=5, capacity=10)
    drive_query = os.environ.get("DOCS_SYNC_DRIVE_QUERY", "")

    stats = run_sync(
        drive_service,
        docs_service,
        store,
        rate_limiter=rate_limiter,
        logger=logger,
        drive_query=drive_query,
    )

    print(
        f"Docs sync complete ({stats.sync_type}): "
        f"{stats.documents_fetched} fetched, {stats.documents_skipped_unchanged} unchanged, "
        f"{stats.documents_trashed} trashed, {stats.parse_failures} parse failures "
        f"in {stats.duration_ms:.0f}ms."
    )


if __name__ == "__main__":
    main()
