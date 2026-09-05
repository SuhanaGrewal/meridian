from __future__ import annotations

import argparse

from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger
from meridian.inbox_intelligence.stale_threads import find_stale_threads
from meridian.ingestion.gmail.store import GmailStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Meridian inbox intelligence utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    stale_parser = subparsers.add_parser(
        "stale-threads", help="List email threads that are waiting on your reply."
    )
    stale_parser.add_argument(
        "--min-days",
        type=int,
        default=3,
        help="Minimum days of silence to count a thread as stale (default: 3).",
    )
    stale_parser.add_argument(
        "--max-days",
        type=int,
        default=None,
        help="Optional cap on days of silence - excludes threads quieter than this "
        "(e.g. --max-days 60 to hide multi-year-old, functionally dead threads).",
    )

    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.inbox_intelligence.cli", log_dir=config.log_dir)

    if args.command == "stale-threads":
        store = GmailStore(config.ingestion_dir / "gmail" / "gmail.db")
        account_email = store.get_account_email()
        if account_email is None:
            print("Account email not captured yet - run `python -m meridian.ingestion.gmail` first.")
            return

        threads = find_stale_threads(
            store, account_email, min_days_quiet=args.min_days, max_days_quiet=args.max_days
        )
        logger.info(
            "stale thread scan complete",
            extra={
                "operation": "inbox_intelligence.stale_threads",
                "status": "success",
                "duration_ms": 0,
                "stale_thread_count": len(threads),
            },
        )

        if not threads:
            print(f"No threads waiting on your reply for {args.min_days}+ days.")
            return

        print(f"{len(threads)} thread(s) waiting on your reply:\n")
        for thread in threads:
            print(f"- [{thread.days_quiet}d quiet] {thread.subject or '(no subject)'} - from {thread.last_sender}")
            print(f"  {thread.last_message_snippet}")
            print()


if __name__ == "__main__":
    main()
