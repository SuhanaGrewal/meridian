from __future__ import annotations

import time
from typing import Callable


class TokenBucket:
    """Blocking token bucket rate limiter. Single-threaded use only (no lock)."""

    def __init__(
        self,
        rate: float,
        capacity: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._rate = rate
        self._capacity = capacity
        self._clock = clock
        self._sleep = sleep
        self._tokens = capacity
        self._last_refill = clock()

    def acquire(self, tokens: float = 1.0) -> None:
        self._refill()
        if self._tokens < tokens:
            shortfall = tokens - self._tokens
            self._sleep(shortfall / self._rate)
            self._refill()
        self._tokens -= tokens

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now
