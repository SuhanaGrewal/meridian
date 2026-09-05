#!/bin/bash
# Installs three macOS launchd agents: full auto-sync (Gmail, Calendar,
# Docs, local files) every 10 minutes, a nightly digest run (which itself
# checks DIGEST_DAYS in .env to decide whether today is a scheduled day),
# and a calendar-notification check every minute (native notification for
# an event starting soon - see CALENDAR_NOTIFY_LEAD_MINUTES in .env).
# Safe to re-run - reloads cleanly if already installed.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
DIGEST_HOUR="${DIGEST_HOUR:-8}"

mkdir -p "$LAUNCH_AGENTS_DIR" "$PROJECT_DIR/logs"
chmod +x "$PROJECT_DIR/scripts/sync_all.sh" "$PROJECT_DIR/scripts/nightly_digest.sh" "$PROJECT_DIR/scripts/calendar_notify.sh"

render() {
    sed \
        -e "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" \
        -e "s|{{DIGEST_HOUR}}|$DIGEST_HOUR|g" \
        "$1"
}

render "$PROJECT_DIR/config/com.meridian.autosync.plist" > "$LAUNCH_AGENTS_DIR/com.meridian.autosync.plist"
render "$PROJECT_DIR/config/com.meridian.nightlydigest.plist" > "$LAUNCH_AGENTS_DIR/com.meridian.nightlydigest.plist"
render "$PROJECT_DIR/config/com.meridian.calendarnotify.plist" > "$LAUNCH_AGENTS_DIR/com.meridian.calendarnotify.plist"

# in case an older install used the gmail-only job name
launchctl unload "$LAUNCH_AGENTS_DIR/com.meridian.gmailsync.plist" 2>/dev/null || true
rm -f "$LAUNCH_AGENTS_DIR/com.meridian.gmailsync.plist"

launchctl unload "$LAUNCH_AGENTS_DIR/com.meridian.autosync.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS_DIR/com.meridian.nightlydigest.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS_DIR/com.meridian.calendarnotify.plist" 2>/dev/null || true

launchctl load -w "$LAUNCH_AGENTS_DIR/com.meridian.autosync.plist"
launchctl load -w "$LAUNCH_AGENTS_DIR/com.meridian.nightlydigest.plist"
launchctl load -w "$LAUNCH_AGENTS_DIR/com.meridian.calendarnotify.plist"

echo "Installed:"
echo "  - Full sync (Gmail, Calendar, Docs, local files) every 10 minutes"
echo "  - Nightly digest at ${DIGEST_HOUR}:00 (set DIGEST_DAYS in .env to restrict which days, e.g. DIGEST_DAYS=mon,wed,fri)"
echo "  - Calendar notifications every minute (set CALENDAR_NOTIFY_LEAD_MINUTES in .env to change the default 15-minute lead time)"
echo ""
echo "Logs: $PROJECT_DIR/logs/launchd-autosync.log, $PROJECT_DIR/logs/launchd-digest.log, and $PROJECT_DIR/logs/launchd-calendarnotify.log"
echo "To change the digest hour: DIGEST_HOUR=7 ./scripts/install_launchd.sh"
echo "To remove all jobs: ./scripts/uninstall_launchd.sh"
