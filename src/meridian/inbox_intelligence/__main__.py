from __future__ import annotations

import argparse

from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger
from meridian.inbox_intelligence.commitments import scan_for_commitments
from meridian.inbox_intelligence.stale_threads import find_stale_threads
from meridian.inbox_intelligence.store import InboxIntelligenceStore
from meridian.ingestion.gmail.store import GmailStore
from meridian.query.anthropic_client import build_client
from meridian.redaction.analyzer import build_analyzer_engine


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

    scan_parser = subparsers.add_parser(
        "scan-commitments",
        help="Scan recent, not-yet-scanned email for soft commitments (costs a small amount of real LLM usage).",
    )
    scan_parser.add_argument(
        "--limit", type=int, default=50, help="Maximum number of messages to scan in this run (default: 50)."
    )
    scan_parser.add_argument(
        "--model", default=None, help="Override the Claude model to use (default: from .env's LLM_MODEL)."
    )

    subparsers.add_parser("commitments", help="List open (unresolved) tracked commitments.")

    resolve_parser = subparsers.add_parser(
        "resolve-commitment", help="Mark a tracked commitment as resolved."
    )
    resolve_parser.add_argument("commitment_id", help="The commitment id shown by the `commitments` command.")

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

    elif args.command == "scan-commitments":
        gmail_store = GmailStore(config.ingestion_dir / "gmail" / "gmail.db")
        account_email = gmail_store.get_account_email()
        if account_email is None:
            print("Account email not captured yet - run `python -m meridian.ingestion.gmail` first.")
            return
        if not config.llm_api_key:
            print("LLM_API_KEY is not set - commitment scanning needs a real Claude call, nothing to do.")
            return

        commitment_store = InboxIntelligenceStore(config.inbox_intelligence_dir / "commitments.db")
        client = build_client(config.llm_api_key)
        analyzer = build_analyzer_engine()

        stats = scan_for_commitments(
            gmail_store, commitment_store, account_email, client, args.model or config.llm_model, analyzer,
            limit=args.limit, logger=logger, audit_log_dir=config.log_dir,
        )
        print(f"Scanned {stats.messages_scanned} message(s), found {stats.commitments_found} commitment(s).")

    elif args.command == "commitments":
        commitment_store = InboxIntelligenceStore(config.inbox_intelligence_dir / "commitments.db")
        open_commitments = commitment_store.list_open_commitments()
        if not open_commitments:
            print("No open commitments.")
            return

        print(f"{len(open_commitments)} open commitment(s):\n")
        for row in open_commitments:
            who = "You" if row["made_by"] == "me" else row["other_party"]
            due = f" (due {row['due_date']})" if row["due_date"] else ""
            print(f"- [{row['commitment_id']}] {who}: {row['description']}{due}")

    elif args.command == "resolve-commitment":
        commitment_store = InboxIntelligenceStore(config.inbox_intelligence_dir / "commitments.db")
        if commitment_store.mark_resolved(args.commitment_id):
            print(f"Marked {args.commitment_id} as resolved.")
        else:
            print(f"No commitment found with id {args.commitment_id}.")


if __name__ == "__main__":
    main()
