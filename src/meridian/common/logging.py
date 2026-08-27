from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_CONFIGURED_LOGGERS: set[str] = set()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "module": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for field in ("operation", "status", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


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
