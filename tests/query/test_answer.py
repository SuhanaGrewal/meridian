from datetime import datetime, timezone

import numpy as np

from meridian.indexing.parent_child import ChunkRecord
from meridian.indexing.store import IndexStore
from meridian.query.answer import ask

_NOW = datetime(2024, 6, 12, 15, 30, tzinfo=timezone.utc)


class _FakeEmbedder:
    def __init__(self, vector):
        self._vector = vector

    def encode(self, texts, batch_size=32, show_progress_bar=False):
        return np.array([self._vector for _ in texts])


class _FakeReranker:
    def __init__(self, scores_by_text):
        self.scores_by_text = scores_by_text

    def predict(self, pairs):
        return [self.scores_by_text.get(text, 0.0) for _, text in pairs]


class _FakeSpan:
    def __init__(self, start, end, entity_type, score=1.0):
        self.start = start
        self.end = end
        self.entity_type = entity_type
        self.score = score


class _FakeAnalyzer:
    """detects one hardcoded name substring - just enough to prove the
    tokenize -> call -> untokenize round trip without needing presidio."""

    def analyze(self, text, entities, language):
        needle = "Jane Doe"
        index = text.find(needle)
        if index == -1:
            return []
        return [_FakeSpan(index, index + len(needle), "PERSON")]


class _FakeMessages:
    def __init__(self, reply_text):
        self.reply_text = reply_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self.reply_text)


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeClient:
    def __init__(self, reply_text):
        self.messages = _FakeMessages(reply_text)


class _RaisingClient:
    """fails the test if the llm is ever called - used to prove abstain is zero-cost."""

    @property
    def messages(self):
        raise AssertionError("the llm must not be called when retrieval abstains")


def _seed_high_confidence_chunk(store, text, query_vec, metadata=None):
    store.upsert_item_chunks(
        "gmail",
        "msg-1",
        [ChunkRecord(text=text, parent_text=text, position=0, is_own_parent=True)],
        [query_vec],
        metadata or {"subject": "Hi", "sent_at": "2024-06-12T00:00:00Z"},
    )


def test_ask_abstains_without_calling_llm_on_empty_index(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    result = ask(
        "anything",
        store=store,
        embedder=_FakeEmbedder(query_vec),
        reranker=_FakeReranker({}),
        analyzer=_FakeAnalyzer(),
        client=_RaisingClient(),
        model="claude-haiku-4-5",
        now=_NOW,
    )

    assert result.abstained is True
    assert result.abstain_reason == "no_candidates"
    assert result.answer is None
    assert result.sources is None


def test_ask_returns_retrieval_only_when_no_client_configured(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    _seed_high_confidence_chunk(store, "quarterly budget report", query_vec)
    reranker = _FakeReranker({"quarterly budget report": 10.0})

    result = ask(
        "budget report",
        store=store,
        embedder=_FakeEmbedder(query_vec),
        reranker=reranker,
        analyzer=_FakeAnalyzer(),
        client=None,
        model="claude-haiku-4-5",
        now=_NOW,
    )

    assert result.abstained is False
    assert result.llm_configured is False
    assert result.answer is None
    assert result.sources is None
    assert len(result.chunks) == 1
    assert result.confidence > 0.99


def test_ask_generates_answer_and_untokenizes_placeholders_back(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    _seed_high_confidence_chunk(
        store,
        "Jane Doe presented the quarterly budget report",
        query_vec,
        metadata={"subject": "Budget", "sender": "a@example.com", "sent_at": "2024-06-12T00:00:00Z"},
    )
    reranker = _FakeReranker({"Jane Doe presented the quarterly budget report": 10.0})
    client = _FakeClient("According to the context, <PERSON_1> presented the report [1].")

    result = ask(
        "who presented the budget report",
        store=store,
        embedder=_FakeEmbedder(query_vec),
        reranker=reranker,
        analyzer=_FakeAnalyzer(),
        client=client,
        model="claude-haiku-4-5",
        now=_NOW,
    )

    assert result.abstained is False
    assert result.llm_configured is True
    assert result.answer == "According to the context, Jane Doe presented the report [1]."
    assert result.sources == "Sources:\n[1] Gmail email from a@example.com, sent 2024-06-12T00:00:00Z, subject: 'Budget'"
    # the tokenized placeholder, never the real name, must be what actually left the machine
    sent_user_message = client.messages.calls[0]["messages"][0]["content"]
    assert "Jane Doe" not in sent_user_message
    assert "<PERSON_1>" in sent_user_message


def test_ask_records_an_audit_event_for_the_external_llm_call(tmp_path):
    import json

    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    _seed_high_confidence_chunk(
        store, "Jane Doe presented the quarterly budget report", query_vec,
        metadata={"subject": "Budget", "sender": "a@example.com", "sent_at": "2024-06-12T00:00:00Z"},
    )
    reranker = _FakeReranker({"Jane Doe presented the quarterly budget report": 10.0})
    client = _FakeClient("An answer [1].")
    audit_log_dir = tmp_path / "logs"

    ask(
        "who presented the budget report",
        store=store, embedder=_FakeEmbedder(query_vec), reranker=reranker,
        analyzer=_FakeAnalyzer(), client=client, model="claude-haiku-4-5",
        now=_NOW, audit_log_dir=audit_log_dir,
    )

    lines = (audit_log_dir / "audit.log").read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event_type"] == "llm.external_call"
    assert entry["detail"]["operation"] == "query.ask"
    assert "entity_counts" in entry["detail"]


def test_ask_low_confidence_abstains_without_calling_llm(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    _seed_high_confidence_chunk(store, "unrelated content", query_vec, metadata={"subject": "x"})
    reranker = _FakeReranker({"unrelated content": -10.0})

    result = ask(
        "unrelated",
        store=store,
        embedder=_FakeEmbedder(query_vec),
        reranker=reranker,
        analyzer=_FakeAnalyzer(),
        client=_RaisingClient(),
        model="claude-haiku-4-5",
        now=_NOW,
    )

    assert result.abstained is True
    assert result.abstain_reason == "low_confidence"
    assert result.answer is None
