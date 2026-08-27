from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class RetryExhaustedError(Exception):
    pass


def retry_with_backoff(
    func: Callable[[], T],
    *,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    logger: logging.Logger | None = None,
    operation: str = "operation",
) -> T:
    attempt = 1
    while True:
        try:
            return func()
        except exceptions as exc:
            if attempt >= max_attempts:
                if logger is not None:
                    logger.error(
                        f"{operation} exhausted retries after {attempt} attempts",
                        extra={"operation": operation, "status": "error", "duration_ms": 0},
                    )
                raise RetryExhaustedError(
                    f"{operation} failed after {max_attempts} attempts"
                ) from exc

            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            if logger is not None:
                logger.warning(
                    f"{operation} attempt {attempt} failed, retrying in {delay}s",
                    extra={"operation": operation, "status": "retry", "duration_ms": 0},
                )
            time.sleep(delay)
            attempt += 1
