import json

import httplib2
import pytest
from googleapiclient.errors import HttpError

from meridian.common.google_api import execute_with_retry
from meridian.common.retry import RetryExhaustedError


def _http_error(status: int, *, retry_after: str | None = None, reason: str | None = None) -> HttpError:
    headers = {"status": str(status)}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    resp = httplib2.Response(headers)

    errors = [{"reason": reason}] if reason else []
    content = json.dumps({"error": {"errors": errors}}).encode("utf-8")
    return HttpError(resp, content)


class _FakeRequest:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    def execute(self):
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_429_with_retry_after_sleeps_then_retries_and_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("meridian.common.google_api.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: sleeps.append(s))

    request = _FakeRequest([_http_error(429, retry_after="12"), "ok"])

    result = execute_with_retry(request, max_attempts=3)

    assert result == "ok"
    assert 12.0 in sleeps


def test_429_without_retry_after_falls_back_to_exponential_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr("meridian.common.google_api.time.sleep", lambda s: sleeps.append(("google_api", s)))
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: sleeps.append(("retry", s)))

    request = _FakeRequest([_http_error(429, reason="rateLimitExceeded"), "ok"])

    result = execute_with_retry(request, max_attempts=3, base_delay=0.1)

    assert result == "ok"
    assert ("retry", 0.1) in sleeps
    assert not any(name == "google_api" for name, _ in sleeps)


def test_quota_403_is_treated_like_a_rate_limit(monkeypatch):
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: None)
    request = _FakeRequest([_http_error(403, reason="userRateLimitExceeded"), "ok"])

    result = execute_with_retry(request, max_attempts=3, base_delay=0.01)

    assert result == "ok"


def test_5xx_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: None)
    request = _FakeRequest([_http_error(503), "ok"])

    result = execute_with_retry(request, max_attempts=3, base_delay=0.01)

    assert result == "ok"


@pytest.mark.parametrize(
    "status,reason",
    [(400, None), (401, None), (403, "insufficientPermissions"), (404, None)],
)
def test_permanent_errors_propagate_without_retry(monkeypatch, status, reason):
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: None)
    request = _FakeRequest([_http_error(status, reason=reason)])

    with pytest.raises(HttpError):
        execute_with_retry(request, max_attempts=3, base_delay=0.01)


def test_connection_timeout_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: None)
    request = _FakeRequest([TimeoutError("The read operation timed out"), "ok"])

    result = execute_with_retry(request, max_attempts=3, base_delay=0.01)

    assert result == "ok"


def test_connection_error_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: None)
    request = _FakeRequest([ConnectionError("connection reset"), "ok"])

    result = execute_with_retry(request, max_attempts=3, base_delay=0.01)

    assert result == "ok"


def test_connection_timeout_exhausts_retries_and_raises(monkeypatch):
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: None)
    request = _FakeRequest([TimeoutError("timeout"), TimeoutError("timeout"), TimeoutError("timeout")])

    with pytest.raises(RetryExhaustedError):
        execute_with_retry(request, max_attempts=3, base_delay=0.01)


def test_retries_exhausted_raises_retry_exhausted_error(monkeypatch):
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: None)
    request = _FakeRequest([_http_error(503), _http_error(503), _http_error(503)])

    with pytest.raises(RetryExhaustedError):
        execute_with_retry(request, max_attempts=3, base_delay=0.01)
