from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_GENESIS_HASH = "0" * 64


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _line_hash(timestamp: str, event_type: str, detail: dict[str, Any], prev_hash: str) -> str:
    payload = {"timestamp": timestamp, "event_type": event_type, "detail": detail, "prev_hash": prev_hash}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _last_hash(path: Path) -> str:
    if not path.exists():
        return _GENESIS_HASH
    last_line = None
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last_line = line
    if last_line is None:
        return _GENESIS_HASH
    return json.loads(last_line)["hash"]


def record_event(log_dir: Path, event_type: str, detail: dict[str, Any] | None = None) -> None:
    """appends one hash-chained entry to log_dir/audit.log - a separate
    file from the operational meridian.log, written directly (not through
    logging.Logger) so it can never be silently dropped or rotated the way
    a log handler might be.

    detail is caller-restricted to counts/metadata by convention, never
    raw content - the same "never log raw values" discipline already
    established in redaction/tokenize.py."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "audit.log"
    detail = detail or {}
    timestamp = _now()
    prev_hash = _last_hash(path)
    entry_hash = _line_hash(timestamp, event_type, detail, prev_hash)
    entry = {
        "timestamp": timestamp,
        "event_type": event_type,
        "detail": detail,
        "prev_hash": prev_hash,
        "hash": entry_hash,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def verify_audit_log(path: Path) -> list[int]:
    """returns the 0-indexed line numbers of any broken hash-chain links -
    an empty list means the file is missing or fully intact.

    each line's own hash is recomputed and compared to its stored hash
    (self-consistency), and its stored prev_hash is compared to the prior
    line's own claimed hash (chain linkage) - a single tampered line
    surfaces as a break starting at the next line unless every subsequent
    line is also rewritten, which is the point of a hash chain."""
    if not path.exists():
        return []

    broken: list[int] = []
    expected_prev_hash = _GENESIS_HASH
    with path.open("r", encoding="utf-8") as f:
        for index, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            recomputed = _line_hash(entry["timestamp"], entry["event_type"], entry["detail"], entry["prev_hash"])
            if recomputed != entry["hash"] or entry["prev_hash"] != expected_prev_hash:
                broken.append(index)
            expected_prev_hash = entry["hash"]
    return broken
