import json

from meridian.security.audit_log import record_event, verify_audit_log


def test_verify_audit_log_missing_file_returns_empty(tmp_path):
    assert verify_audit_log(tmp_path / "audit.log") == []


def test_record_event_creates_file_with_one_valid_entry(tmp_path):
    record_event(tmp_path, "auth.consent_granted", {"scope_count": 4})

    path = tmp_path / "audit.log"
    assert path.exists()
    entry = json.loads(path.read_text().strip())
    assert entry["event_type"] == "auth.consent_granted"
    assert entry["detail"] == {"scope_count": 4}
    assert entry["prev_hash"] == "0" * 64
    assert verify_audit_log(path) == []


def test_record_event_defaults_detail_to_empty_dict(tmp_path):
    record_event(tmp_path, "auth.token_refreshed")

    entry = json.loads((tmp_path / "audit.log").read_text().strip())
    assert entry["detail"] == {}


def test_multi_line_chain_is_intact(tmp_path):
    record_event(tmp_path, "auth.consent_granted", {"scope_count": 4})
    record_event(tmp_path, "llm.external_call", {"entity_counts": {"PERSON": 1}})
    record_event(tmp_path, "digest.reviewed", {"decision": "approved"})

    path = tmp_path / "audit.log"
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 3

    entries = [json.loads(line) for line in lines]
    assert entries[1]["prev_hash"] == entries[0]["hash"]
    assert entries[2]["prev_hash"] == entries[1]["hash"]
    assert verify_audit_log(path) == []


def test_tampering_with_a_line_content_is_detected(tmp_path):
    record_event(tmp_path, "auth.consent_granted", {"scope_count": 4})
    record_event(tmp_path, "llm.external_call", {"entity_counts": {"PERSON": 1}})

    path = tmp_path / "audit.log"
    lines = path.read_text().strip().splitlines()
    tampered = json.loads(lines[0])
    tampered["detail"] = {"scope_count": 999}  # edited without recomputing hash
    lines[0] = json.dumps(tampered)
    path.write_text("\n".join(lines) + "\n")

    broken = verify_audit_log(path)

    assert 0 in broken


def test_tampering_recomputing_only_that_lines_hash_breaks_the_next_line(tmp_path):
    record_event(tmp_path, "auth.consent_granted", {"scope_count": 4})
    record_event(tmp_path, "llm.external_call", {"entity_counts": {"PERSON": 1}})

    path = tmp_path / "audit.log"
    lines = path.read_text().strip().splitlines()
    tampered = json.loads(lines[0])
    tampered["detail"] = {"scope_count": 999}
    from meridian.security.audit_log import _line_hash

    tampered["hash"] = _line_hash(
        tampered["timestamp"], tampered["event_type"], tampered["detail"], tampered["prev_hash"]
    )
    lines[0] = json.dumps(tampered)
    path.write_text("\n".join(lines) + "\n")

    broken = verify_audit_log(path)

    # line 0 is now internally self-consistent (its own hash matches its
    # own content), but line 1's prev_hash no longer matches line 0's new
    # hash - the break surfaces one line later, exactly as the hash chain
    # is supposed to reveal.
    assert 0 not in broken
    assert 1 in broken


def test_record_event_appends_without_overwriting_prior_entries(tmp_path):
    record_event(tmp_path, "auth.consent_granted", {})
    record_event(tmp_path, "auth.token_refreshed", {})

    lines = (tmp_path / "audit.log").read_text().strip().splitlines()
    assert len(lines) == 2
