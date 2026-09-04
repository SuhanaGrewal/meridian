import json

import pytest

from meridian.common import logging as logging_module
from meridian.common.logging import get_logger, log_operation, register_secret


def _log_lines(log_dir):
    return (log_dir / "meridian.log").read_text().splitlines()


def test_log_operation_success_emits_json_with_required_fields(tmp_path):
    logger = get_logger("test.logging.success", log_dir=tmp_path)

    with log_operation(logger, "fetch_messages"):
        pass

    lines = _log_lines(tmp_path)
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["module"] == "test.logging.success"
    assert payload["operation"] == "fetch_messages"
    assert payload["status"] == "success"
    assert "timestamp" in payload
    assert isinstance(payload["duration_ms"], (int, float))


def test_log_operation_failure_emits_error_status_and_reraises(tmp_path):
    logger = get_logger("test.logging.failure", log_dir=tmp_path)

    class Boom(Exception):
        pass

    try:
        with log_operation(logger, "fetch_messages"):
            raise Boom("network error")
    except Boom:
        pass
    else:
        raise AssertionError("expected Boom to propagate")

    lines = _log_lines(tmp_path)
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["status"] == "error"
    assert payload["operation"] == "fetch_messages"
    assert "exc_info" in payload


@pytest.fixture(autouse=True)
def _reset_registered_secrets():
    original = list(logging_module._REGISTERED_SECRETS)
    logging_module._REGISTERED_SECRETS.clear()
    yield
    logging_module._REGISTERED_SECRETS[:] = original


def test_register_secret_scrubs_it_from_subsequent_log_output(tmp_path):
    register_secret("super-secret-api-key")
    logger = get_logger("test.logging.scrub", log_dir=tmp_path)

    logger.info("using key super-secret-api-key to call the API")

    lines = _log_lines(tmp_path)
    payload = json.loads(lines[0])
    assert "super-secret-api-key" not in payload["message"]
    assert "[SCRUBBED]" in payload["message"]


def test_register_secret_scrubs_values_in_extra_fields_too(tmp_path):
    register_secret("nested-secret-value")
    logger = get_logger("test.logging.scrub_extra", log_dir=tmp_path)

    logger.info("call made", extra={"detail": {"header": "Bearer nested-secret-value"}})

    lines = _log_lines(tmp_path)
    payload = json.loads(lines[0])
    assert "nested-secret-value" not in json.dumps(payload)
    assert "[SCRUBBED]" in payload["detail"]["header"]


def test_register_secret_ignores_empty_string():
    register_secret("")

    assert "" not in logging_module._REGISTERED_SECRETS


def test_unset_empty_secret_never_triggers_scrubbing(tmp_path):
    register_secret("")  # simulates an unset LLM_API_KEY/client_secret
    logger = get_logger("test.logging.no_scrub", log_dir=tmp_path)

    logger.info("a perfectly normal message")

    lines = _log_lines(tmp_path)
    payload = json.loads(lines[0])
    assert payload["message"] == "a perfectly normal message"


def test_register_secret_does_not_duplicate_the_same_value():
    register_secret("dup-secret")
    register_secret("dup-secret")

    assert logging_module._REGISTERED_SECRETS.count("dup-secret") == 1
