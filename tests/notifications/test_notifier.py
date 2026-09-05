import subprocess
from unittest.mock import patch

from meridian.notifications.notifier import send_native_notification


def test_send_native_notification_calls_osascript_with_title_and_message():
    with patch("meridian.notifications.notifier.subprocess.run") as mock_run:
        result = send_native_notification("Standup", "Starts at 9:10 AM")

    assert result is True
    args = mock_run.call_args[0][0]
    assert args[0] == "osascript"
    assert args[1] == "-e"
    assert "Standup" in args[2]
    assert "Starts at 9:10 AM" in args[2]


def test_send_native_notification_escapes_double_quotes():
    with patch("meridian.notifications.notifier.subprocess.run") as mock_run:
        send_native_notification('Meeting "Q3 Review"', "now")

    script = mock_run.call_args[0][0][2]
    assert '\\"Q3 Review\\"' in script


def test_send_native_notification_returns_false_and_does_not_raise_when_osascript_fails():
    with patch("meridian.notifications.notifier.subprocess.run", side_effect=subprocess.CalledProcessError(1, "osascript")):
        result = send_native_notification("Standup", "Starts at 9:10 AM")

    assert result is False


def test_send_native_notification_returns_false_when_osascript_missing():
    with patch("meridian.notifications.notifier.subprocess.run", side_effect=OSError("not found")):
        result = send_native_notification("Standup", "Starts at 9:10 AM")

    assert result is False
