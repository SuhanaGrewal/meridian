from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_CONFIGURED_LOGGERS: set[str] = set()

_BASE_RECORD_ATTRS = set(logging.makeLogRecord({}).__dict__.keys())

_REGISTERED_SECRETS: list[str] = []


def register_secret(value: str) -> None:
    """registers a value to be scrubbed from every log line - defense in
    depth against a future accidental logger.info(f"...{api_key}...").
    skips falsy values: an unset (empty-string) secret must never be
    registered, or _scrub would replace every occurrence of "" in every
    string and corrupt all log output."""
    if value and value not in _REGISTERED_SECRETS:
        _REGISTERED_SECRETS.append(value)


def _scrub(value):
    if isinstance(value, str):
        for secret in _REGISTERED_SECRETS:
            value = value.replace(secret, "[SCRUBBED]")
        return value
    if isinstance(value, dict):
        return {key: _scrub(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "module": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        # any field passed via logger.info(..., extra={...}) ends up as a
        # plain attribute on the record. copying everything not part of the
        # standard LogRecord shape means callers can log new metrics
        # (operation, status, duration_ms, or whatever a future phase needs)
        # without this formatter needing to know their names in advance.
        for key, value in record.__dict__.items():
            if key not in _BASE_RECORD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        payload = _scrub(payload)
        return json.dumps(payload, default=str)


def get_logger(name: str, log_dir: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _CONFIGURED_LOGGERS:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler: logging.Handler
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_dir / "meridian.log")
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)

    _CONFIGURED_LOGGERS.add(name)
    return logger


@contextmanager
def log_operation(logger: logging.Logger, operation: str) -> Iterator[None]:
    start = time.monotonic()
    try:
        yield
    except Exception:
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        logger.error(
            f"{operation} failed",
            extra={"operation": operation, "status": "error", "duration_ms": duration_ms},
            exc_info=True,
        )
        raise
    else:
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info(
            f"{operation} succeeded",
            extra={"operation": operation, "status": "success", "duration_ms": duration_ms},
        )
