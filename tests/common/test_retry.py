import pytest

from meridian.common.retry import RetryExhaustedError, retry_with_backoff


class TransientError(Exception):
    pass


def test_retry_succeeds_after_transient_failures(monkeypatch):
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda _: None)

    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise TransientError("not yet")
        return "ok"

    result = retry_with_backoff(flaky, exceptions=(TransientError,), max_attempts=5)

    assert result == "ok"
    assert calls["count"] == 3


def test_retry_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda _: None)

    calls = {"count": 0}

    def always_fails():
        calls["count"] += 1
        raise TransientError("still broken")

    with pytest.raises(RetryExhaustedError):
        retry_with_backoff(always_fails, exceptions=(TransientError,), max_attempts=3)

    assert calls["count"] == 3


def test_retry_does_not_catch_unrelated_exceptions(monkeypatch):
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda _: None)

    def raises_value_error():
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        retry_with_backoff(raises_value_error, exceptions=(TransientError,), max_attempts=3)
