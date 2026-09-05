#!/bin/bash
# Removes the launchd agents installed by install_launchd.sh (including
# the older gmail-only job name, if present from before autosync covered
# every source).
set -euo pipefail

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

launchctl unload "$LAUNCH_AGENTS_DIR/com.meridian.gmailsync.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS_DIR/com.meridian.autosync.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS_DIR/com.meridian.nightlydigest.plist" 2>/dev/null || true

rm -f "$LAUNCH_AGENTS_DIR/com.meridian.gmailsync.plist" \
      "$LAUNCH_AGENTS_DIR/com.meridian.autosync.plist" \
      "$LAUNCH_AGENTS_DIR/com.meridian.nightlydigest.plist"

echo "Removed Meridian's scheduled sync and nightly digest jobs."
