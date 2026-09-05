from __future__ import annotations

import argparse
from datetime import datetime, timezone

from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger
from meridian.ingestion.calendar.store import CalendarStore
from meridian.notifications.calendar_watch import check_upcoming_events
from meridian.notifications.notifier import send_native_notification
from meridian.notifications.store import NotificationStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "One-shot check for calendar events starting soon, firing a native "
            "notification for each new one. Meant to be invoked frequently (e.g. "
            "every minute via launchd) rather than run once - see "
            "scripts/calendar_notify.sh and config/com.meridian.calendarnotify.plist."
        )
    )
    parser.add_argument("command", choices=["check"])
    parser.add_argument(
        "--lead-minutes", type=int, default=15,
        help="How many minutes ahead of an event's start to notify (default: 15).",
    )
    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.notifications.cli", log_dir=config.log_dir)

    calendar_store = CalendarStore(config.ingestion_dir / "calendar" / "calendar.db")
    notification_store = NotificationStore(config.notifications_dir / "notifications.db")

    now = datetime.now(tz=timezone.utc)
    events = check_upcoming_events(calendar_store, notification_store, now=now, lead_minutes=args.lead_minutes)

    for event in events:
        sent = send_native_notification(f"Starting soon: {event.summary}", f"Starts at {event.start_at}", logger=logger)
        if sent:
            logger.info(
                "calendar notification sent",
                extra={"operation": "notifications.calendar_watch", "status": "success", "duration_ms": 0},
            )

    print(f"{len(events)} new notification(s) sent.")


if __name__ == "__main__":
    main()
