from dataclasses import dataclass

from meridian.query.history import check_open_questions, record_question
from meridian.query.history_store import QueryHistoryStore


class _FakeAnalyzer:
    def analyze(self, text, entities, language):
        return []


class _FakeMessages:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._replies.pop(0))


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeClient:
    def __init__(self, replies):
        self.messages = _FakeMessages(replies)


@dataclass
class _FakeAnswerResult:
    abstained: bool
    answer: str | None


def test_record_question_classifies_waiting_and_stores_it(tmp_path):
    store = QueryHistoryStore(tmp_path / "history.db")
    client = _FakeClient(["YES"])

    question_id = record_question(
        "did I get a reply from Nick", store, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer()
    )

    row = store.get_question(question_id)
    assert row["is_waiting"] == 1


def test_record_question_classifies_non_waiting_and_stores_it(tmp_path):
    store = QueryHistoryStore(tmp_path / "history.db")
    client = _FakeClient(["NO"])

    question_id = record_question(
        "when is my flight", store, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer()
    )

    row = store.get_question(question_id)
    assert row["is_waiting"] == 0


def test_check_open_questions_marks_resolved_when_verdict_says_so(tmp_path):
    store = QueryHistoryStore(tmp_path / "history.db")
    question_id = store.add_question("did I get a reply from Nick", is_waiting=True)
    client = _FakeClient(["RESOLVED"])

    def ask_fn(question_text):
        return _FakeAnswerResult(abstained=False, answer="Nick replied yesterday confirming the meeting.")

    still_open = check_open_questions(
        store, ask_fn=ask_fn, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer()
    )

    assert still_open == []
    assert store.get_question(question_id)["resolved"] == 1


def test_check_open_questions_keeps_open_when_verdict_says_pending(tmp_path):
    store = QueryHistoryStore(tmp_path / "history.db")
    store.add_question("did I get a reply from Nick", is_waiting=True, asked_at="2024-06-01T00:00:00+00:00")
    client = _FakeClient(["PENDING"])

    def ask_fn(question_text):
        return _FakeAnswerResult(abstained=False, answer="No new messages from Nick found.")

    still_open = check_open_questions(
        store, ask_fn=ask_fn, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer()
    )

    assert still_open == [{"question_text": "did I get a reply from Nick", "asked_at": "2024-06-01T00:00:00+00:00"}]


def test_check_open_questions_keeps_open_when_ask_abstains_without_calling_verdict_llm(tmp_path):
    store = QueryHistoryStore(tmp_path / "history.db")
    store.add_question("did I get a reply from Nick", is_waiting=True, asked_at="2024-06-01T00:00:00+00:00")
    client = _FakeClient([])  # any .create() call would raise IndexError

    def ask_fn(question_text):
        return _FakeAnswerResult(abstained=True, answer=None)

    still_open = check_open_questions(
        store, ask_fn=ask_fn, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer()
    )

    assert len(still_open) == 1


def test_check_open_questions_skips_already_resolved_and_non_waiting(tmp_path):
    store = QueryHistoryStore(tmp_path / "history.db")
    resolved_id = store.add_question("already handled", is_waiting=True)
    store.mark_resolved(resolved_id)
    store.add_question("plain fact question", is_waiting=False)
    client = _FakeClient([])  # no open waiting questions - no .create() call should happen

    still_open = check_open_questions(
        store, ask_fn=lambda q: _FakeAnswerResult(abstained=True, answer=None),
        client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(),
    )

    assert still_open == []
