#!/bin/bash
# Removes the two launchd agents installed by install_launchd.sh.
set -euo pipefail

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

launchctl unload "$LAUNCH_AGENTS_DIR/com.meridian.gmailsync.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS_DIR/com.meridian.nightlydigest.plist" 2>/dev/null || true

rm -f "$LAUNCH_AGENTS_DIR/com.meridian.gmailsync.plist" "$LAUNCH_AGENTS_DIR/com.meridian.nightlydigest.plist"

echo "Removed Meridian's scheduled Gmail sync and nightly digest jobs."
