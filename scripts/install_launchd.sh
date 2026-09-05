#!/bin/bash
# Installs two macOS launchd agents: Gmail sync every 10 minutes, and a
# nightly digest run (which itself checks DIGEST_DAYS in .env to decide
# whether today is a scheduled day). Safe to re-run - reloads cleanly if
# already installed.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
DIGEST_HOUR="${DIGEST_HOUR:-8}"

mkdir -p "$LAUNCH_AGENTS_DIR" "$PROJECT_DIR/logs"
chmod +x "$PROJECT_DIR/scripts/sync_gmail.sh" "$PROJECT_DIR/scripts/nightly_digest.sh"

render() {
    sed \
        -e "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" \
        -e "s|{{DIGEST_HOUR}}|$DIGEST_HOUR|g" \
        "$1"
}

render "$PROJECT_DIR/config/com.meridian.gmailsync.plist" > "$LAUNCH_AGENTS_DIR/com.meridian.gmailsync.plist"
render "$PROJECT_DIR/config/com.meridian.nightlydigest.plist" > "$LAUNCH_AGENTS_DIR/com.meridian.nightlydigest.plist"

launchctl unload "$LAUNCH_AGENTS_DIR/com.meridian.gmailsync.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS_DIR/com.meridian.nightlydigest.plist" 2>/dev/null || true

launchctl load -w "$LAUNCH_AGENTS_DIR/com.meridian.gmailsync.plist"
launchctl load -w "$LAUNCH_AGENTS_DIR/com.meridian.nightlydigest.plist"

echo "Installed:"
echo "  - Gmail sync every 10 minutes"
echo "  - Nightly digest at ${DIGEST_HOUR}:00 (set DIGEST_DAYS in .env to restrict which days, e.g. DIGEST_DAYS=mon,wed,fri)"
echo ""
echo "Logs: $PROJECT_DIR/logs/launchd-gmailsync.log and $PROJECT_DIR/logs/launchd-digest.log"
echo "To change the digest hour: DIGEST_HOUR=7 ./scripts/install_launchd.sh"
echo "To remove both jobs: ./scripts/uninstall_launchd.sh"
