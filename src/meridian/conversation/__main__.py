from __future__ import annotations

import argparse

from meridian.common.config import ensure_dirs, load_config
from meridian.conversation.store import ConversationStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Manage conversation threads - normally reached by "
            "`python -m meridian.query \"<text>\" --thread <name>`; "
            "this CLI is a direct escape hatch for the same store."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="Show a thread's turns so far.")
    list_parser.add_argument("thread", help="Thread name.")

    clear_parser = subparsers.add_parser("clear", help="Delete a thread's history, starting it fresh.")
    clear_parser.add_argument("thread", help="Thread name.")

    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    store = ConversationStore(config.conversation_dir / "conversations.db")

    if args.command == "list":
        turns = store.list_turns(args.thread)
        if not turns:
            print(f"No turns yet in thread '{args.thread}'.")
            return
        for turn in turns:
            speaker = "You" if turn["role"] == "user" else "Meridian"
            print(f"{speaker}: {turn['content']}\n")

    elif args.command == "clear":
        store.clear_conversation(args.thread)
        print(f"Cleared thread '{args.thread}'.")


if __name__ == "__main__":
    main()
