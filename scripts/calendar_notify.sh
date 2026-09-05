#!/bin/bash
# Wrapper invoked every minute by the com.meridian.calendarnotify launchd
# job - a one-shot check each time, not a long-running process (see
# notifications/calendar_watch.py for why). CALENDAR_NOTIFY_LEAD_MINUTES
# in .env overrides the default 15-minute lead time.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

LEAD_MINUTES="15"
if [ -f "$PROJECT_DIR/.env" ]; then
    configured="$(grep -E '^CALENDAR_NOTIFY_LEAD_MINUTES=' "$PROJECT_DIR/.env" | tail -1 | cut -d= -f2-)"
    if [ -n "$configured" ]; then
        LEAD_MINUTES="$configured"
    fi
fi

"$PROJECT_DIR/.venv/bin/python" -m meridian.notifications check --lead-minutes "$LEAD_MINUTES"
