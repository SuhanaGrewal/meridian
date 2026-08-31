from __future__ import annotations

from typing import Any


def _extract_when(node: dict[str, Any] | None) -> tuple[str | None, bool]:
    """extracts a start/end node ({'date': ...} or {'dateTime': ...}) into (iso_string, is_all_day)."""
    if not node:
        return None, False
    if "date" in node:
        return node["date"], True
    if "dateTime" in node:
        return node["dateTime"], False
    return None, False
