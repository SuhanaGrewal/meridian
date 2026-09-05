from __future__ import annotations

import argparse
from datetime import datetime, timezone

from meridian.common.config import ensure_dirs, load_config
from meridian.ingestion.calendar.store import CalendarStore
from meridian.reminders.scheduling import propose_free_slot
from meridian.reminders.store import ReminderStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Meridian reminder intake - normally reached by just texting the router "
            "(query.__main__) something imperative like 'remind me to meet with Nick'; "
            "this CLI is a direct escape hatch for the same store."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a reminder and propose a free calendar slot for it.")
    add_parser.add_argument("text", help="The reminder text (wrap in quotes).")

    subparsers.add_parser("list", help="List pending reminders.")

    dismiss_parser = subparsers.add_parser("dismiss", help="Mark a reminder as done/dismissed.")
    dismiss_parser.add_argument("reminder_id", help="The reminder id shown by the `list` command.")

    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    store = ReminderStore(config.reminders_dir / "reminders.db")

    if args.command == "add":
        calendar_store = CalendarStore(config.ingestion_dir / "calendar" / "calendar.db")
        now = datetime.now(tz=timezone.utc)
        slot = propose_free_slot(calendar_store, now=now)
        slot_start, slot_end = (slot[0].isoformat(), slot[1].isoformat()) if slot else (None, None)

        reminder_id = store.add_reminder(args.text, proposed_slot_start=slot_start, proposed_slot_end=slot_end)
        print(f"Added reminder [{reminder_id}]: {args.text}")
        if slot is not None:
            print(f"Proposed free slot: {slot_start} to {slot_end} (nothing booked - suggestion only).")
        else:
            print("No open slot found in the next week - nothing proposed.")

    elif args.command == "list":
        pending = store.list_pending_reminders()
        if not pending:
            print("No pending reminders.")
            return
        print(f"{len(pending)} pending reminder(s):\n")
        for row in pending:
            slot = (
                f" (proposed: {row['proposed_slot_start']} to {row['proposed_slot_end']})"
                if row["proposed_slot_start"]
                else ""
            )
            print(f"- [{row['reminder_id']}] {row['reminder_text']}{slot}")

    elif args.command == "dismiss":
        if store.dismiss(args.reminder_id):
            print(f"Dismissed {args.reminder_id}.")
        else:
            print(f"No reminder found with id {args.reminder_id}.")


if __name__ == "__main__":
    main()
