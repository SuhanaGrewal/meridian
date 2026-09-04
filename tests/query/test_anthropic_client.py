import anthropic
import httpx2
import pytest

from meridian.common.retry import RetryExhaustedError
from meridian.query.anthropic_client import _is_retryable, build_client, call_claude


def _status_error(cls, status_code: int):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status_code, request=request)
    return cls("error", response=response, body=None)


class _FakeTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text: str):
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _FakeClient:
    def __init__(self, responses: list):
        self.messages = _FakeMessages(responses)


def test_build_client_disables_sdk_retries():
    client = build_client("fake-api-key")

    assert client.max_retries == 0


def test_rate_limit_error_is_retryable():
    assert _is_retryable(_status_error(anthropic.RateLimitError, 429)) is True


def test_server_error_is_retryable():
    assert _is_retryable(_status_error(anthropic.InternalServerError, 500)) is True
    assert _is_retryable(_status_error(anthropic.ServiceUnavailableError, 503)) is True


def test_connection_error_is_retryable():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.APIConnectionError(request=request)

    assert _is_retryable(exc) is True


def test_bad_request_is_not_retryable():
    assert _is_retryable(_status_error(anthropic.BadRequestError, 400)) is False


def test_authentication_error_is_not_retryable():
    assert _is_retryable(_status_error(anthropic.AuthenticationError, 401)) is False


def test_not_found_is_not_retryable():
    assert _is_retryable(_status_error(anthropic.NotFoundError, 404)) is False


def test_unrelated_exception_is_not_retryable():
    assert _is_retryable(ValueError("something else")) is False


def test_call_claude_returns_text_on_first_success():
    client = _FakeClient([_FakeResponse("hello there")])

    result = call_claude(
        client, model="claude-haiku-4-5", system="be helpful", user_message="hi"
    )

    assert result == "hello there"
    assert client.messages.calls == [
        {
            "model": "claude-haiku-4-5",
            "max_tokens": 1024,
            "system": "be helpful",
            "messages": [{"role": "user", "content": "hi"}],
        }
    ]


def test_call_claude_retries_transient_error_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    client = _FakeClient(
        [
            _status_error(anthropic.RateLimitError, 429),
            _status_error(anthropic.InternalServerError, 500),
            _FakeResponse("recovered"),
        ]
    )

    result = call_claude(
        client, model="claude-haiku-4-5", system="be helpful", user_message="hi"
    )

    assert result == "recovered"
    assert len(client.messages.calls) == 3


def test_call_claude_raises_retry_exhausted_after_max_attempts(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    client = _FakeClient([_status_error(anthropic.RateLimitError, 429) for _ in range(5)])

    with pytest.raises(RetryExhaustedError):
        call_claude(client, model="claude-haiku-4-5", system="be helpful", user_message="hi")

    assert len(client.messages.calls) == 5


def test_call_claude_raises_immediately_on_bad_request(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    client = _FakeClient([_status_error(anthropic.BadRequestError, 400)])

    with pytest.raises(anthropic.BadRequestError):
        call_claude(client, model="claude-haiku-4-5", system="be helpful", user_message="hi")

    assert len(client.messages.calls) == 1
