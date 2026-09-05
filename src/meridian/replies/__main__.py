from __future__ import annotations

import argparse

from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger
from meridian.ingestion.gmail.store import GmailStore
from meridian.query.anthropic_client import build_client
from meridian.redaction.analyzer import build_analyzer_engine
from meridian.replies.drafting import MessageNotFoundError, draft_reply_for_message
from meridian.replies.store import DraftStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Draft-only reply generation (#11) - drafts in the user's own voice, "
            "adjusted by relationship to the sender. Nothing is ever sent; "
            "'approve' just marks a draft ready for a future send step that "
            "does not exist yet in this project."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    draft_parser = subparsers.add_parser("draft", help="Draft a reply to a specific message.")
    draft_parser.add_argument("message_id", help="The Gmail message id to draft a reply to.")
    draft_parser.add_argument(
        "--model", default=None, help="Override the Claude model to use (default: from .env's LLM_MODEL)."
    )

    subparsers.add_parser("list", help="List pending drafts.")

    show_parser = subparsers.add_parser("show", help="Show a draft's full text.")
    show_parser.add_argument("draft_id")

    edit_parser = subparsers.add_parser("edit", help="Replace a draft's text.")
    edit_parser.add_argument("draft_id")
    edit_parser.add_argument("text", help="The new draft text (wrap in quotes).")

    approve_parser = subparsers.add_parser("approve", help="Mark a draft approved (does not send it).")
    approve_parser.add_argument("draft_id")

    reject_parser = subparsers.add_parser("reject", help="Mark a draft rejected.")
    reject_parser.add_argument("draft_id")

    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.replies.cli", log_dir=config.log_dir)
    draft_store = DraftStore(config.replies_dir / "drafts.db")

    if args.command == "draft":
        gmail_store = GmailStore(config.ingestion_dir / "gmail" / "gmail.db")
        account_email = gmail_store.get_account_email()
        if account_email is None:
            print("Account email not captured yet - run `python -m meridian.ingestion.gmail` first.")
            return
        if not config.llm_api_key:
            print("LLM_API_KEY is not set - drafting needs a real Claude call, nothing to do.")
            return

        client = build_client(config.llm_api_key)
        analyzer = build_analyzer_engine()
        try:
            draft_id = draft_reply_for_message(
                gmail_store, draft_store, account_email, args.message_id,
                client=client, model=args.model or config.llm_model, analyzer=analyzer,
                logger=logger, audit_log_dir=config.log_dir,
            )
        except MessageNotFoundError:
            print(f"No message found with id {args.message_id}.")
            return

        draft = draft_store.get_draft(draft_id)
        print(f"Draft [{draft_id}] (nothing sent - review before approving):\n")
        print(draft["draft_text"])

    elif args.command == "list":
        pending = draft_store.list_pending_drafts()
        if not pending:
            print("No pending drafts.")
            return
        print(f"{len(pending)} pending draft(s):\n")
        for row in pending:
            preview = row["draft_text"][:80].replace("\n", " ")
            print(f"- [{row['draft_id']}] to {row['recipient_email']}: {preview}...")

    elif args.command == "show":
        draft = draft_store.get_draft(args.draft_id)
        if draft is None:
            print(f"No draft found with id {args.draft_id}.")
            return
        print(f"Status: {draft['status']}\n")
        print(draft["draft_text"])

    elif args.command == "edit":
        if draft_store.update_draft_text(args.draft_id, args.text):
            print(f"Updated draft {args.draft_id}.")
        else:
            print(f"No draft found with id {args.draft_id}.")

    elif args.command == "approve":
        if draft_store.approve(args.draft_id):
            print(f"Approved {args.draft_id} (not sent - no send capability exists yet).")
        else:
            print(f"No draft found with id {args.draft_id}.")

    elif args.command == "reject":
        if draft_store.reject(args.draft_id):
            print(f"Rejected {args.draft_id}.")
        else:
            print(f"No draft found with id {args.draft_id}.")


if __name__ == "__main__":
    main()
