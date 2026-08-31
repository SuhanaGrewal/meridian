from __future__ import annotations

import argparse
import os

from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger
from meridian.common.rate_limiter import TokenBucket
from meridian.ingestion.gmail.client import build_gmail_service
from meridian.ingestion.gmail.store import GmailStore
from meridian.ingestion.gmail.sync import run_sync


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Gmail messages into Meridian's local store (readonly)."
    )
    parser.add_argument(
        "--full-resync",
        action="store_true",
        help="Ignore any stored history id and re-run a full backfill from scratch.",
    )
    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.ingestion.gmail.cli", log_dir=config.log_dir)

    store = GmailStore(config.ingestion_dir / "gmail" / "gmail.db")
    if args.full_resync:
        store.clear_sync_state()

    service = build_gmail_service(config=config)
    rate_limiter = TokenBucket(rate=5, capacity=10)
    query = os.environ.get("GMAIL_SYNC_QUERY", "")

    stats = run_sync(service, store, rate_limiter=rate_limiter, logger=logger, query=query)

    print(
        f"Gmail sync complete ({stats.sync_type}): "
        f"{stats.messages_fetched} fetched, {stats.messages_updated} updated, "
        f"{stats.messages_deleted} deleted, {stats.parse_failures} parse failures "
        f"in {stats.duration_ms:.0f}ms."
    )


if __name__ == "__main__":
    main()
