import sqlite3
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from langgraph.checkpoint.sqlite import SqliteSaver

from meridian.digest.orchestrator import review_digest_job, run_digest_job
from meridian.digest.store import DigestStore

_NOW = datetime(2024, 6, 10, tzinfo=timezone.utc)
_KEY = Fernet.generate_key()


def _gmail_row():
    return {
        "sender": "jane@example.com", "sent_at": "2024-06-05T00:00:00Z", "subject": "Budget", "body_text": "hello",
        "label_ids": '["INBOX"]',
    }


class _FakeStores:
    def __init__(self, gmail=None, calendar=None, docs=None, notes=None, entities=None):
        self.gmail = gmail or []
        self.calendar = calendar or []
        self.docs = docs or []
        self.notes = notes or []
        self.entities = entities or []

    def list_messages_since(self, since):
        return self.gmail

    def list_events_upcoming(self, now, lookahead_end):
        return self.calendar

    def list_docs_modified_since(self, since):
        return self.docs

    def list_notes_updated_since(self, since):
        return self.notes

    def list_entities_mentioned_since(self, since):
        return self.entities


class _FakeAnalyzer:
    def analyze(self, text, entities, language):
        return []


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, reply_text="Digest summary [1]."):
        self.reply_text = reply_text
        self.call_count = 0

    def create(self, **kwargs):
        self.call_count += 1
        return _FakeResponse(self.reply_text)


class _FakeClient:
    def __init__(self, reply_text="Digest summary [1]."):
        self.messages = _FakeMessages(reply_text)


def _run_kwargs(tmp_path, stores, client, digest_store, checkpointer):
    return dict(
        digest_store=digest_store,
        gmail_store=stores, calendar_store=stores, docs_store=stores, notes_store=stores, entity_store=stores,
        analyzer=_FakeAnalyzer(), client=client, model="claude-haiku-4-5", checkpointer=checkpointer,
    )


def _setup(tmp_path, *, gmail=None, client=None):
    digest_store = DigestStore(tmp_path / "digest.db", encryption_key=_KEY)
    conn = sqlite3.connect(tmp_path / "checkpoints.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    stores = _FakeStores(gmail=gmail)
    return digest_store, checkpointer, stores, conn


def test_nothing_new_advances_cursor_and_creates_no_run(tmp_path):
    digest_store, checkpointer, stores, conn = _setup(tmp_path)

    result = run_digest_job(now=_NOW, **_run_kwargs(tmp_path, stores, _FakeClient(), digest_store, checkpointer))

    assert result.status == "nothing_new"
    assert result.run_id is None
    assert digest_store.count_runs() == 0
    assert digest_store.get_cursor() == _NOW.isoformat()
    conn.close()


def test_awaiting_review_creates_a_pending_run(tmp_path):
    digest_store, checkpointer, stores, conn = _setup(tmp_path, gmail=[_gmail_row()])

    result = run_digest_job(now=_NOW, **_run_kwargs(tmp_path, stores, _FakeClient(), digest_store, checkpointer))

    assert result.status == "awaiting_review"
    assert result.run_id is not None
    run = digest_store.get_run(result.run_id)
    assert run["status"] == "pending"
    assert digest_store.get_cursor() is None  # cursor does not advance until reviewed
    conn.close()


def test_no_llm_configured_produces_plaintext_digest(tmp_path):
    digest_store, checkpointer, stores, conn = _setup(tmp_path, gmail=[_gmail_row()])

    result = run_digest_job(now=_NOW, **_run_kwargs(tmp_path, stores, None, digest_store, checkpointer))

    assert result.status == "awaiting_review"
    run = digest_store.get_run(result.run_id)
    assert run["llm_used"] == 0
    assert "gmail:" in run["digest_text"]
    conn.close()


def test_run_refuses_to_start_while_a_run_is_pending(tmp_path):
    digest_store, checkpointer, stores, conn = _setup(tmp_path, gmail=[_gmail_row()])
    client = _FakeClient()
    first = run_digest_job(now=_NOW, **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer))
    assert first.status == "awaiting_review"

    second = run_digest_job(
        now=_NOW + timedelta(hours=1), **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer)
    )

    assert second.status == "skipped_pending"
    assert second.run_id == first.run_id
    assert digest_store.count_runs() == 1  # no duplicate run created
    assert client.messages.call_count == 1  # no second LLM call
    conn.close()


def test_review_approve_marks_run_approved_and_advances_cursor(tmp_path):
    digest_store, checkpointer, stores, conn = _setup(tmp_path, gmail=[_gmail_row()])
    client = _FakeClient()
    run = run_digest_job(now=_NOW, **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer))

    result = review_digest_job(
        run_id=run.run_id, approve=True, **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer)
    )

    assert result.status == "approved"
    stored = digest_store.get_run(run.run_id)
    assert stored["status"] == "approved"
    assert stored["decided_at"] is not None
    assert digest_store.get_cursor() == stored["window_end"]
    conn.close()


def test_review_records_a_digest_reviewed_audit_event(tmp_path):
    import json

    digest_store, checkpointer, stores, conn = _setup(tmp_path, gmail=[_gmail_row()])
    client = _FakeClient()
    audit_log_dir = tmp_path / "logs"
    run = run_digest_job(now=_NOW, **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer))

    review_digest_job(
        run_id=run.run_id, approve=True, audit_log_dir=audit_log_dir,
        **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer),
    )

    lines = (audit_log_dir / "audit.log").read_text().strip().splitlines()
    entries = [json.loads(line) for line in lines]
    assert len(entries) == 1
    assert entries[0]["event_type"] == "digest.reviewed"
    assert entries[0]["detail"] == {"run_id": run.run_id, "decision": "approved"}
    conn.close()


def test_review_reject_marks_run_rejected_and_still_advances_cursor(tmp_path):
    digest_store, checkpointer, stores, conn = _setup(tmp_path, gmail=[_gmail_row()])
    client = _FakeClient()
    run = run_digest_job(now=_NOW, **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer))

    result = review_digest_job(
        run_id=run.run_id, approve=False, **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer)
    )

    assert result.status == "rejected"
    stored = digest_store.get_run(run.run_id)
    assert stored["status"] == "rejected"
    assert digest_store.get_cursor() == stored["window_end"]
    conn.close()


def test_review_unknown_run_id_returns_not_found(tmp_path):
    digest_store, checkpointer, stores, conn = _setup(tmp_path)

    result = review_digest_job(
        run_id="does-not-exist", approve=True, **_run_kwargs(tmp_path, stores, _FakeClient(), digest_store, checkpointer)
    )

    assert result.status == "not_found"
    conn.close()


def test_review_already_decided_run_is_not_reprocessed(tmp_path):
    digest_store, checkpointer, stores, conn = _setup(tmp_path, gmail=[_gmail_row()])
    client = _FakeClient()
    run = run_digest_job(now=_NOW, **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer))
    review_digest_job(run_id=run.run_id, approve=True, **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer))

    result = review_digest_job(
        run_id=run.run_id, approve=False, **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer)
    )

    assert result.status == "already_decided"
    assert digest_store.get_run(run.run_id)["status"] == "approved"  # unchanged
    conn.close()


def test_run_after_approval_starts_a_fresh_window(tmp_path):
    digest_store, checkpointer, stores, conn = _setup(tmp_path, gmail=[_gmail_row()])
    client = _FakeClient()
    first = run_digest_job(now=_NOW, **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer))
    review_digest_job(run_id=first.run_id, approve=True, **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer))

    # simulates nothing new having appeared since the cursor advanced -
    # a fresh run should be allowed to start (the pending guard is gone)
    # and correctly report nothing_new rather than refusing outright.
    stores.gmail = []
    second = run_digest_job(
        now=_NOW + timedelta(hours=1), **_run_kwargs(tmp_path, stores, client, digest_store, checkpointer)
    )

    assert second.status == "nothing_new"
    conn.close()
