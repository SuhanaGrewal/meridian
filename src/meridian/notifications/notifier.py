from __future__ import annotations

import logging
import subprocess


def _escape_for_applescript(text: str) -> str:
    """AppleScript string literals use double quotes with backslash
    escaping - a calendar event summary is real user data (could contain
    quotes or backslashes), so this must be escaped before being
    interpolated into the -e script rather than trusted verbatim."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def send_native_notification(title: str, message: str, *, logger: logging.Logger | None = None) -> bool:
    """fires a native macOS notification via osascript - no extra
    dependency needed, this ships with every Mac. Returns False (and logs
    a warning, never raises) if osascript isn't available or fails, since
    a missed notification shouldn't crash the calling check."""
    script = f'display notification "{_escape_for_applescript(message)}" with title "{_escape_for_applescript(title)}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=10)
        return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        if logger is not None:
            logger.warning(
                "failed to send native notification",
                extra={"operation": "notifications.send", "status": "error", "duration_ms": 0},
                exc_info=True,
            )
        return False
