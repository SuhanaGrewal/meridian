from datetime import datetime, timezone

import numpy as np

from meridian.indexing.parent_child import ChunkRecord
from meridian.indexing.store import IndexStore
from meridian.query.retrieval import _fetch_and_filter_candidates, retrieve


class _FakeReranker:
    """returns a canned score per call, keyed by call order - scores map
    1:1 to the order `rerank()` passes texts in."""

    def __init__(self, scores_by_text):
        self.scores_by_text = scores_by_text

    def predict(self, pairs):
        return [self.scores_by_text.get(text, 0.0) for _, text in pairs]


def _seed(store, source, item_id, records, metadata):
    embeddings = [np.zeros(4, dtype=np.float32) for _ in records]
    store.upsert_item_chunks(source, item_id, records, embeddings, metadata)


def test_fetch_and_filter_resolves_chunk_ids_to_rows(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    _seed(
        store, "gmail", "msg-1",
        [ChunkRecord(text="hello", parent_text="hello", position=0, is_own_parent=True)],
        {"subject": "Hi", "sender": "a@example.com", "sent_at": "2024-06-12T00:00:00Z"},
    )

    rows = _fetch_and_filter_candidates(store, ["gmail:msg-1:0000"], None)

    assert len(rows) == 1
    assert rows[0]["chunk_text"] == "hello"


def test_fetch_and_filter_skips_unknown_chunk_ids(tmp_path):
    store = IndexStore(tmp_path / "index.db")

    rows = _fetch_and_filter_candidates(store, ["gmail:does-not-exist:0000"], None)

    assert rows == []


def test_fetch_and_filter_applies_date_range(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    _seed(
        store, "gmail", "msg-in-range",
        [ChunkRecord(text="a", parent_text="a", position=0, is_own_parent=True)],
        {"sent_at": "2024-06-12T00:00:00Z"},
    )
    _seed(
        store, "gmail", "msg-out-of-range",
        [ChunkRecord(text="b", parent_text="b", position=0, is_own_parent=True)],
        {"sent_at": "2024-01-01T00:00:00Z"},
    )
    date_range = (datetime(2024, 6, 10, tzinfo=timezone.utc), datetime(2024, 6, 17, tzinfo=timezone.utc))

    rows = _fetch_and_filter_candidates(
        store, ["gmail:msg-in-range:0000", "gmail:msg-out-of-range:0000"], date_range
    )

    assert len(rows) == 1
    assert rows[0]["source_item_id"] == "msg-in-range"


def test_fetch_and_filter_docs_survive_date_range_with_no_date_metadata(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    _seed(
        store, "docs", "doc-1",
        [ChunkRecord(text="content", parent_text="content", position=0, is_own_parent=True)],
        {"title": "My Doc"},
    )
    date_range = (datetime(2024, 6, 10, tzinfo=timezone.utc), datetime(2024, 6, 17, tzinfo=timezone.utc))

    rows = _fetch_and_filter_candidates(store, ["docs:doc-1:0000"], date_range)

    assert len(rows) == 1


def test_fetch_and_filter_dedups_children_sharing_a_parent(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    shared_parent = "a long parent context shared by two children"
    records = [
        ChunkRecord(text="child one", parent_text=shared_parent, position=0, is_own_parent=False),
        ChunkRecord(text="child two", parent_text=shared_parent, position=1, is_own_parent=False),
    ]
    _seed(store, "gmail", "msg-1", records, {"subject": "Hi"})

    rows = _fetch_and_filter_candidates(
        store, ["gmail:msg-1:0000", "gmail:msg-1:0001"], None
    )

    assert len(rows) == 1
    assert rows[0]["parent_text"] == shared_parent


def test_retrieve_returns_high_confidence_result(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    store.upsert_item_chunks(
        "gmail", "msg-1",
        [ChunkRecord(text="quarterly budget report", parent_text="quarterly budget report", position=0, is_own_parent=True)],
        [query_vec],
        {"subject": "Budget", "sent_at": "2024-06-12T00:00:00Z"},
    )
    reranker = _FakeReranker({"quarterly budget report": 10.0})

    result = retrieve(store, "budget report", query_vec, reranker=reranker)

    assert result.abstained is False
    assert result.abstain_reason is None
    assert len(result.chunks) == 1
    assert result.chunks[0].source == "gmail"
    assert result.confidence > 0.99


def test_retrieve_on_empty_index_abstains_no_candidates(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    reranker = _FakeReranker({})

    result = retrieve(store, "anything", np.zeros(4, dtype=np.float32), reranker=reranker)

    assert result.abstained is True
    assert result.abstain_reason == "no_candidates"
    assert result.chunks == []


def test_retrieve_date_range_emptying_pool_gives_distinct_abstain_reason(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    store.upsert_item_chunks(
        "gmail", "msg-1",
        [ChunkRecord(text="old budget report", parent_text="old budget report", position=0, is_own_parent=True)],
        [query_vec],
        {"sent_at": "2020-01-01T00:00:00Z"},
    )
    reranker = _FakeReranker({"old budget report": 10.0})
    date_range = (datetime(2024, 6, 10, tzinfo=timezone.utc), datetime(2024, 6, 17, tzinfo=timezone.utc))

    result = retrieve(store, "budget report", query_vec, reranker=reranker, date_range=date_range)

    assert result.abstained is True
    assert result.abstain_reason == "no_candidates_in_date_range"


def test_retrieve_low_confidence_abstains_but_still_returns_chunks(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    store.upsert_item_chunks(
        "gmail", "msg-1",
        [ChunkRecord(text="unrelated content", parent_text="unrelated content", position=0, is_own_parent=True)],
        [query_vec],
        {"subject": "unrelated content"},
    )
    reranker = _FakeReranker({"unrelated content": -10.0})

    result = retrieve(store, "unrelated", query_vec, reranker=reranker)

    assert result.abstained is True
    assert result.abstain_reason == "low_confidence"
    assert len(result.chunks) == 1  # still surfaced, just marked low-confidence


def test_retrieve_respects_top_k(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    scores = {}
    for i in range(5):
        text = f"budget item {i}"
        store.upsert_item_chunks(
            "gmail", f"msg-{i}",
            [ChunkRecord(text=text, parent_text=text, position=0, is_own_parent=True)],
            [query_vec],
            {"subject": text},
        )
        scores[text] = 5.0 + i

    result = retrieve(store, "budget item", query_vec, reranker=_FakeReranker(scores), top_k=2)

    assert len(result.chunks) == 2
    # highest-scoring items first
    assert result.chunks[0].confidence >= result.chunks[1].confidence


def test_fetch_and_filter_keeps_distinct_parents(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    _seed(
        store, "gmail", "msg-1",
        [ChunkRecord(text="a", parent_text="parent A", position=0, is_own_parent=True)],
        {},
    )
    _seed(
        store, "gmail", "msg-2",
        [ChunkRecord(text="b", parent_text="parent B", position=0, is_own_parent=True)],
        {},
    )

    rows = _fetch_and_filter_candidates(
        store, ["gmail:msg-1:0000", "gmail:msg-2:0000"], None
    )

    assert len(rows) == 2
