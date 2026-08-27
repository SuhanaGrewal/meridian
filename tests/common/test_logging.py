import json

from meridian.common.logging import get_logger, log_operation


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
