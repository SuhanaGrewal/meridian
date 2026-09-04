from cryptography.fernet import Fernet

from meridian.digest.store import DigestStore

_KEY = Fernet.generate_key()


def test_create_run_defaults_to_pending(tmp_path):
    store = DigestStore(tmp_path / "digest.db", encryption_key=_KEY)

    store.create_run("run-1", "2024-06-01T00:00:00Z", "2024-06-02T00:00:00Z", "digest text", "Sources:\n[1] x", 3, True)

    run = store.get_run("run-1")
    assert run["status"] == "pending"
    assert run["digest_text"] == "digest text"
    assert run["item_count"] == 3
    assert run["llm_used"] == 1
    assert run["decided_at"] is None


def test_digest_text_and_sources_text_are_encrypted_on_disk(tmp_path):
    db_path = tmp_path / "digest.db"
    store = DigestStore(db_path, encryption_key=_KEY)
    store.create_run("run-1", "s1", "e1", "sensitive digest content", "Sources:\n[1] a@example.com", 1, True)

    import sqlite3

    raw_conn = sqlite3.connect(db_path)
    raw_row = raw_conn.execute(
        "SELECT digest_text, sources_text FROM digest_runs WHERE run_id = 'run-1'"
    ).fetchone()
    raw_conn.close()

    assert "sensitive digest content" not in raw_row[0]
    assert "a@example.com" not in raw_row[1]
    # the store's own read path still returns plaintext
    assert store.get_run("run-1")["digest_text"] == "sensitive digest content"


def test_get_run_returns_none_when_missing(tmp_path):
    store = DigestStore(tmp_path / "digest.db", encryption_key=_KEY)

    assert store.get_run("does-not-exist") is None


def test_get_pending_run_returns_none_when_empty(tmp_path):
    store = DigestStore(tmp_path / "digest.db", encryption_key=_KEY)

    assert store.get_pending_run() is None


def test_get_pending_run_returns_the_oldest_pending_run(tmp_path):
    store = DigestStore(tmp_path / "digest.db", encryption_key=_KEY)
    store.create_run("run-1", "s1", "e1", "text-1", "sources-1", 1, False)
    store.create_run("run-2", "s2", "e2", "text-2", "sources-2", 1, False)

    pending = store.get_pending_run()

    assert pending["run_id"] == "run-1"


def test_list_pending_runs_excludes_decided_runs(tmp_path):
    store = DigestStore(tmp_path / "digest.db", encryption_key=_KEY)
    store.create_run("run-1", "s1", "e1", "text-1", "sources-1", 1, False)
    store.create_run("run-2", "s2", "e2", "text-2", "sources-2", 1, False)
    store.mark_approved("run-1")

    pending = store.list_pending_runs()

    assert [row["run_id"] for row in pending] == ["run-2"]


def test_mark_approved_sets_status_and_decided_at(tmp_path):
    store = DigestStore(tmp_path / "digest.db", encryption_key=_KEY)
    store.create_run("run-1", "s1", "e1", "text", "sources", 1, False)

    store.mark_approved("run-1")

    run = store.get_run("run-1")
    assert run["status"] == "approved"
    assert run["decided_at"] is not None


def test_mark_rejected_sets_status_and_decided_at(tmp_path):
    store = DigestStore(tmp_path / "digest.db", encryption_key=_KEY)
    store.create_run("run-1", "s1", "e1", "text", "sources", 1, False)

    store.mark_rejected("run-1")

    run = store.get_run("run-1")
    assert run["status"] == "rejected"
    assert run["decided_at"] is not None


def test_cursor_round_trip(tmp_path):
    store = DigestStore(tmp_path / "digest.db", encryption_key=_KEY)

    assert store.get_cursor() is None

    store.set_cursor("2024-06-01T00:00:00Z")

    assert store.get_cursor() == "2024-06-01T00:00:00Z"


def test_set_cursor_overwrites_previous_value(tmp_path):
    store = DigestStore(tmp_path / "digest.db", encryption_key=_KEY)
    store.set_cursor("2024-06-01T00:00:00Z")

    store.set_cursor("2024-06-02T00:00:00Z")

    assert store.get_cursor() == "2024-06-02T00:00:00Z"


def test_count_runs_by_status(tmp_path):
    store = DigestStore(tmp_path / "digest.db", encryption_key=_KEY)
    store.create_run("run-1", "s1", "e1", "text-1", "sources-1", 1, False)
    store.create_run("run-2", "s2", "e2", "text-2", "sources-2", 1, False)
    store.mark_approved("run-1")

    assert store.count_runs() == 2
    assert store.count_runs("pending") == 1
    assert store.count_runs("approved") == 1
    assert store.count_runs("rejected") == 0
