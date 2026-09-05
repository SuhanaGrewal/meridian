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
    assert result.sources == (
        "Sources:\n[1] Gmail email from a@example.com, sent 2024-06-12T00:00:00Z (today), subject: 'Budget'"
    )
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


def test_ask_low_confidence_abstain_with_no_client_never_calls_llm(tmp_path):
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
        client=None,
        model="claude-haiku-4-5",
        now=_NOW,
    )

    assert result.abstained is True
    assert result.abstain_reason == "low_confidence"
    assert result.answer is None


def test_ask_low_confidence_tiebreak_confirms_no_still_abstains(tmp_path):
    # the reranker scored it too low to trust, and the LLM tiebreak agrees
    # it's not actually relevant - correctly still abstains, just via one
    # extra confirming call rather than a raw score cutoff alone.
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    _seed_high_confidence_chunk(store, "unrelated content", query_vec, metadata={"subject": "x"})
    reranker = _FakeReranker({"unrelated content": -10.0})
    client = _FakeClient("NO")

    result = ask(
        "unrelated",
        store=store,
        embedder=_FakeEmbedder(query_vec),
        reranker=reranker,
        analyzer=_FakeAnalyzer(),
        client=client,
        model="claude-haiku-4-5",
        now=_NOW,
    )

    assert result.abstained is True
    assert result.abstain_reason == "low_confidence"
    assert result.answer is None
    assert len(client.messages.calls) == 1


def test_ask_low_confidence_tiebreak_confirms_yes_answers_anyway(tmp_path):
    # the reranker scored the genuinely-correct top candidate too low to
    # trust on its own - the LLM tiebreak confirms it's actually relevant,
    # so this should un-abstain and generate an answer from just that one
    # confirmed chunk, not the full unfiltered candidate pool.
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    _seed_high_confidence_chunk(
        store, "the laptop drop-off is at the office on Tuesday", query_vec,
        metadata={"subject": "IT Kit", "sender": "billy@example.com", "sent_at": "2024-06-01T00:00:00Z"},
    )
    reranker = _FakeReranker({"the laptop drop-off is at the office on Tuesday": -10.0})
    client = _FakeMultiReplyClient(["YES", "You need to drop it off at the office on Tuesday [1]."])

    result = ask(
        "where do I drop off my laptop",
        store=store, embedder=_FakeEmbedder(query_vec), reranker=reranker,
        analyzer=_FakeAnalyzer(), client=client, model="claude-haiku-4-5", now=_NOW,
    )

    assert result.abstained is False
    assert result.answer == "You need to drop it off at the office on Tuesday [1]."
    assert len(result.chunks) == 1
    assert len(client.messages.calls) == 2


def test_ask_forward_looking_query_falls_back_to_past_match_when_nothing_upcoming(tmp_path):
    # "next week" (2024-06-17 to 2024-06-24) excludes this past-dated
    # chunk entirely - the fallback (unfiltered) search should still find
    # it and let the LLM frame "nothing upcoming, here's your last one"
    # using the existing recency-labeling machinery, rather than just
    # abstaining because the strict date filter found nothing.
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    _seed_high_confidence_chunk(
        store, "Flight booking confirmation for your trip", query_vec,
        metadata={"subject": "Flight", "sender": "airline@example.com", "sent_at": "2024-05-01T00:00:00Z"},
    )
    reranker = _FakeReranker({"Flight booking confirmation for your trip": 10.0})
    client = _FakeClient("There's nothing upcoming, but your last flight was on May 1st [1].")

    result = ask(
        "any upcoming flight bookings next week",
        store=store, embedder=_FakeEmbedder(query_vec), reranker=reranker,
        analyzer=_FakeAnalyzer(), client=client, model="claude-haiku-4-5", now=_NOW,
    )

    assert result.abstained is False
    assert result.answer == "There's nothing upcoming, but your last flight was on May 1st [1]."
    assert len(result.chunks) == 1


def test_ask_forward_looking_query_abstains_with_no_upcoming_match_when_nothing_at_all(tmp_path):
    # a past-dated, unrelated chunk exists (so hybrid search finds
    # something and the date filter is what actually excludes it - not an
    # empty index), but it's a poor semantic match even once the date
    # filter is lifted in the fallback, and the LLM tiebreak agrees it's
    # not relevant either - nothing usable in either direction, so this
    # should land on the more specific "no_upcoming_match" reason, not
    # the generic "no_candidates".
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    _seed_high_confidence_chunk(
        store, "unrelated old content", query_vec,
        metadata={"subject": "x", "sent_at": "2024-05-01T00:00:00Z"},
    )
    reranker = _FakeReranker({"unrelated old content": -10.0})
    client = _FakeClient("NO")

    result = ask(
        "any upcoming flight bookings next week",
        store=store, embedder=_FakeEmbedder(query_vec), reranker=reranker,
        analyzer=_FakeAnalyzer(), client=client, model="claude-haiku-4-5", now=_NOW,
    )

    assert result.abstained is True
    assert result.abstain_reason == "no_upcoming_match"
    assert result.answer is None


def test_ask_backward_looking_query_does_not_fall_back(tmp_path):
    # "last week" found nothing in range - unlike a forward-looking query,
    # this should NOT retry unfiltered, since surfacing an unrelated item
    # from some other time as a substitute for "last week" wouldn't make
    # sense to the user.
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    _seed_high_confidence_chunk(
        store, "Flight booking confirmation for your trip", query_vec,
        metadata={"subject": "Flight", "sender": "airline@example.com", "sent_at": "2024-05-01T00:00:00Z"},
    )
    reranker = _FakeReranker({"Flight booking confirmation for your trip": 10.0})

    result = ask(
        "what happened last week", store=store, embedder=_FakeEmbedder(query_vec), reranker=reranker,
        analyzer=_FakeAnalyzer(), client=_RaisingClient(), model="claude-haiku-4-5", now=_NOW,
    )

    assert result.abstained is True
    assert result.abstain_reason == "no_candidates_in_date_range"
