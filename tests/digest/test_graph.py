import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from meridian.digest.graph import build_digest_graph
from meridian.query.history_store import QueryHistoryStore

_INITIAL_STATE = {
    "window_start": "2024-06-01T00:00:00Z",
    "window_end": "2024-06-10T00:00:00Z",
    "lookahead_end": "2024-06-17T00:00:00Z",
}


def _gmail_row():
    return {
        "sender": "jane@example.com", "sent_at": "2024-06-05T00:00:00Z", "subject": "Budget", "body_text": "hello",
        "label_ids": '["INBOX"]',
    }


class _FakeStores:
    """implements all five store read methods gather_items() calls - one
    instance is passed for all five store parameters, since each param is
    only ever called through its own specific method name."""

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
    def __init__(self, reply_text):
        self.reply_text = reply_text
        self.call_count = 0

    def create(self, **kwargs):
        self.call_count += 1
        return _FakeResponse(self.reply_text)


class _FakeClient:
    def __init__(self, reply_text="Digest summary [1]."):
        self.messages = _FakeMessages(reply_text)


def _build_graph(tmp_path, *, stores, client, db_name="checkpoints.db", audit_log_dir=None):
    conn = sqlite3.connect(tmp_path / db_name, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    graph = build_digest_graph(
        stores, stores, stores, stores, stores, _FakeAnalyzer(), client, "claude-haiku-4-5", checkpointer,
        audit_log_dir=audit_log_dir,
    )
    return graph, conn


def test_nothing_new_short_circuits_without_interrupt(tmp_path):
    stores = _FakeStores()
    graph, conn = _build_graph(tmp_path, stores=stores, client=_FakeClient())

    result = graph.invoke(_INITIAL_STATE, config={"configurable": {"thread_id": "run-empty"}})

    assert "__interrupt__" not in result
    assert result["digest_text"] == ""
    assert result["llm_used"] is False
    conn.close()


def test_no_llm_configured_uses_plaintext_digest_and_still_pauses(tmp_path):
    stores = _FakeStores(gmail=[_gmail_row()])
    graph, conn = _build_graph(tmp_path, stores=stores, client=None)

    result = graph.invoke(_INITIAL_STATE, config={"configurable": {"thread_id": "run-1"}})

    assert "__interrupt__" in result
    assert result["llm_used"] is False
    assert "gmail:" in result["digest_text"]
    conn.close()


def test_llm_configured_generates_summary_and_pauses(tmp_path):
    stores = _FakeStores(gmail=[_gmail_row()])
    client = _FakeClient("Digest summary [1].")
    graph, conn = _build_graph(tmp_path, stores=stores, client=client)

    result = graph.invoke(_INITIAL_STATE, config={"configurable": {"thread_id": "run-1"}})

    assert "__interrupt__" in result
    assert result["llm_used"] is True
    assert result["digest_text"] == "Digest summary [1]."
    conn.close()


def test_pause_and_resume_across_separate_checkpointer_connections(tmp_path):
    stores = _FakeStores(gmail=[_gmail_row()])
    client = _FakeClient()
    config = {"configurable": {"thread_id": "run-1"}}

    graph1, conn1 = _build_graph(tmp_path, stores=stores, client=client)
    result = graph1.invoke(_INITIAL_STATE, config=config)
    assert "__interrupt__" in result
    conn1.close()

    # simulate a brand-new process: fresh connection, fresh checkpointer, fresh graph
    graph2, conn2 = _build_graph(tmp_path, stores=stores, client=client)

    snapshot = graph2.get_state(config)
    assert snapshot.next == ("review",)

    final = graph2.invoke(Command(resume=True), config=config)

    assert final["decision"] is True
    conn2.close()


def test_llm_called_exactly_once_across_pause_and_resume(tmp_path):
    stores = _FakeStores(gmail=[_gmail_row()])
    client = _FakeClient()
    config = {"configurable": {"thread_id": "run-1"}}
    graph, conn = _build_graph(tmp_path, stores=stores, client=client)

    graph.invoke(_INITIAL_STATE, config=config)
    graph.invoke(Command(resume=True), config=config)

    assert client.messages.call_count == 1
    conn.close()


def test_summarize_records_an_audit_event_when_llm_is_called(tmp_path):
    import json

    stores = _FakeStores(gmail=[_gmail_row()])
    client = _FakeClient("Digest summary [1].")
    audit_log_dir = tmp_path / "logs"
    graph, conn = _build_graph(tmp_path, stores=stores, client=client, audit_log_dir=audit_log_dir)

    graph.invoke(_INITIAL_STATE, config={"configurable": {"thread_id": "run-1"}})

    lines = (audit_log_dir / "audit.log").read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event_type"] == "llm.external_call"
    assert entry["detail"]["operation"] == "digest.summarize"
    conn.close()


def test_no_llm_configured_records_no_audit_event(tmp_path):
    stores = _FakeStores(gmail=[_gmail_row()])
    audit_log_dir = tmp_path / "logs"
    graph, conn = _build_graph(tmp_path, stores=stores, client=None, audit_log_dir=audit_log_dir)

    graph.invoke(_INITIAL_STATE, config={"configurable": {"thread_id": "run-1"}})

    assert not (audit_log_dir / "audit.log").exists()
    conn.close()


def test_resume_with_false_routes_to_rejected(tmp_path):
    stores = _FakeStores(gmail=[_gmail_row()])
    client = _FakeClient()
    config = {"configurable": {"thread_id": "run-1"}}
    graph, conn = _build_graph(tmp_path, stores=stores, client=client)

    graph.invoke(_INITIAL_STATE, config=config)
    final = graph.invoke(Command(resume=False), config=config)

    assert final["decision"] is False
    conn.close()


class _FakeMultiReplyMessages:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._replies.pop(0))


class _FakeMultiReplyClient:
    def __init__(self, replies):
        self.messages = _FakeMultiReplyMessages(replies)


class _FakeAskResult:
    def __init__(self, abstained, answer):
        self.abstained = abstained
        self.answer = answer


def test_gather_includes_still_open_follow_up_question(tmp_path):
    stores = _FakeStores()
    history_store = QueryHistoryStore(tmp_path / "history.db")
    history_store.add_question("did I get a reply from Nick", is_waiting=True, asked_at="2024-06-01T00:00:00Z")
    client = _FakeMultiReplyClient(["PENDING", "Digest summary [1]."])

    def ask_fn(question_text):
        return _FakeAskResult(abstained=False, answer="No new messages found.")

    conn = sqlite3.connect(tmp_path / "checkpoints.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    graph = build_digest_graph(
        stores, stores, stores, stores, stores, _FakeAnalyzer(), client, "claude-haiku-4-5", checkpointer,
        history_store=history_store, ask_fn=ask_fn,
    )

    result = graph.invoke(_INITIAL_STATE, config={"configurable": {"thread_id": "run-followup"}})

    assert "__interrupt__" in result
    followup_items = [item for item in result["items"] if item["source"] == "query_history"]
    assert len(followup_items) == 1
    assert "did I get a reply from Nick" in followup_items[0]["label"]
    assert len(history_store.list_open_waiting_questions()) == 1
    conn.close()


def test_gather_marks_resolved_question_resolved_and_excludes_it(tmp_path):
    # no gmail/calendar/etc. data and the one open question resolves, so
    # items ends up empty and the run correctly short-circuits to
    # nothing_new - proving the resolved question doesn't linger as a
    # gathered item, not just that it's absent from a populated list.
    stores = _FakeStores()
    history_store = QueryHistoryStore(tmp_path / "history.db")
    history_store.add_question("did I get a reply from Nick", is_waiting=True, asked_at="2024-06-01T00:00:00Z")
    client = _FakeMultiReplyClient(["RESOLVED"])

    def ask_fn(question_text):
        return _FakeAskResult(abstained=False, answer="Nick replied yesterday confirming the meeting.")

    conn = sqlite3.connect(tmp_path / "checkpoints.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    graph = build_digest_graph(
        stores, stores, stores, stores, stores, _FakeAnalyzer(), client, "claude-haiku-4-5", checkpointer,
        history_store=history_store, ask_fn=ask_fn,
    )

    result = graph.invoke(_INITIAL_STATE, config={"configurable": {"thread_id": "run-followup-resolved"}})

    assert "__interrupt__" not in result
    assert result["items"] == []
    assert history_store.list_open_waiting_questions() == []
    conn.close()


def test_gather_without_history_store_makes_no_extra_llm_calls(tmp_path):
    stores = _FakeStores(gmail=[_gmail_row()])
    client = _FakeClient("Digest summary [1].")
    graph, conn = _build_graph(tmp_path, stores=stores, client=client)

    graph.invoke(_INITIAL_STATE, config={"configurable": {"thread_id": "run-no-history"}})

    assert client.messages.call_count == 1
    conn.close()
