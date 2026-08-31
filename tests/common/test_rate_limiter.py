from meridian.common.rate_limiter import TokenBucket


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_acquire_consumes_tokens_immediately_when_available():
    clock = FakeClock()
    bucket = TokenBucket(rate=1.0, capacity=5.0, clock=clock.time, sleep=clock.sleep)

    bucket.acquire(3.0)

    assert bucket.available_tokens == 2.0
    assert clock.now == 0.0


def test_acquire_sleeps_for_shortfall_when_bucket_empty():
    clock = FakeClock()
    bucket = TokenBucket(rate=2.0, capacity=5.0, clock=clock.time, sleep=clock.sleep)

    bucket.acquire(5.0)
    bucket.acquire(2.0)

    assert clock.now == 1.0
    assert bucket.available_tokens == 0.0


def test_refill_accumulates_over_elapsed_time_capped_at_capacity():
    clock = FakeClock()
    bucket = TokenBucket(rate=1.0, capacity=3.0, clock=clock.time, sleep=clock.sleep)

    bucket.acquire(3.0)
    clock.now += 10.0

    assert bucket.available_tokens == 3.0
