from __future__ import annotations

import logging

import anthropic

from meridian.common.retry import retry_with_backoff


def build_client(api_key: str) -> anthropic.Anthropic:
    """builds the anthropic client with the sdk's own retry disabled -
    retries are driven entirely through this project's retry_with_backoff
    instead, mirroring common/google_api.py::execute_with_retry. the sdk's
    internal retry is invisible to this project's structured logger and
    would double-stack backoff underneath this project's own if left on."""
    return anthropic.Anthropic(api_key=api_key, max_retries=0)


class _TransientAnthropicError(Exception):
    pass


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, anthropic.RateLimitError):
        return True
    if isinstance(exc, anthropic.APIConnectionError):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code >= 500
    return False


def call_claude(
    client: anthropic.Anthropic,
    *,
    model: str,
    system: str,
    user_message: str,
    max_tokens: int = 1024,
    logger: logging.Logger | None = None,
) -> str:
    """sends one message to claude and returns its text reply.

    retries transient errors (429, 5xx, connection failures) through this
    project's own retry_with_backoff; anything else (e.g. a 4xx caused by a
    bad request) propagates immediately, unretried."""

    def attempt() -> str:
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:
            if _is_retryable(exc):
                raise _TransientAnthropicError(str(exc)) from exc
            raise
        return next(block.text for block in response.content if block.type == "text")

    return retry_with_backoff(
        attempt,
        exceptions=(_TransientAnthropicError,),
        logger=logger,
        operation="anthropic_call",
    )
