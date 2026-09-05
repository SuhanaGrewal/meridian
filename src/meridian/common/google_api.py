from __future__ import annotations

import json
import logging
import time
from typing import Any, Protocol

from googleapiclient.errors import HttpError

from meridian.common.rate_limiter import TokenBucket
from meridian.common.retry import retry_with_backoff

_RETRYABLE_SERVER_ERRORS = {500, 502, 503, 504}
_QUOTA_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"}


class RateLimitedError(Exception):
    def __init__(self, retry_after: float | None = None):
        super().__init__(f"rate limited (retry_after={retry_after})")
        self.retry_after = retry_after


class TransientHttpError(Exception):
    pass


class _Executable(Protocol):
    def execute(self) -> Any: ...


def execute_with_retry(
    request: _Executable,
    *,
    rate_limiter: TokenBucket | None = None,
    logger: logging.Logger | None = None,
    operation: str = "google_api_call",
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Any:
    """Executes a Google API request, handling throttling and transient errors.

    429s (and quota-flavored 403s) honor the server's Retry-After duration
    exactly, then still go through retry_with_backoff for attempt-counting
    and its own exponential delay. 5xx errors are retried the same way.
    Everything else (400/401/non-quota 403/404) propagates immediately.

    A raw connection-level failure (TimeoutError, ConnectionError - the
    request never got as far as an HTTP response at all) is just as
    transient as a 5xx and is retried the same way, rather than crashing
    the whole sync on one network blip.
    """

    def attempt() -> Any:
        if rate_limiter is not None:
            rate_limiter.acquire()
        try:
            return request.execute()
        except HttpError as exc:
            status = _status(exc)

            if status == 429 or (status == 403 and _is_quota_error(exc)):
                retry_after = _retry_after_seconds(exc)
                if retry_after is not None:
                    if logger is not None:
                        logger.warning(
                            f"{operation} rate-limited, honoring Retry-After",
                            extra={
                                "operation": operation,
                                "status": "retry",
                                "duration_ms": retry_after * 1000,
                            },
                        )
                    time.sleep(retry_after)
                raise RateLimitedError(retry_after) from exc

            if status in _RETRYABLE_SERVER_ERRORS:
                raise TransientHttpError(str(exc)) from exc

            raise
        except (TimeoutError, ConnectionError) as exc:
            raise TransientHttpError(str(exc)) from exc

    return retry_with_backoff(
        attempt,
        exceptions=(RateLimitedError, TransientHttpError),
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        logger=logger,
        operation=operation,
    )


def _status(exc: HttpError) -> int | None:
    return getattr(exc.resp, "status", None)


def _retry_after_seconds(exc: HttpError) -> float | None:
    resp = getattr(exc, "resp", None)
    if resp is None:
        return None
    value = resp.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_quota_error(exc: HttpError) -> bool:
    content = getattr(exc, "content", None)
    if not content:
        return False
    try:
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        payload = json.loads(text)
    except (ValueError, AttributeError):
        return False

    errors = payload.get("error", {}).get("errors", [])
    reasons = {item.get("reason") for item in errors}
    return bool(reasons & _QUOTA_REASONS)
