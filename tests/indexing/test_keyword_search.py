import numpy as np

from meridian.indexing.keyword_search import search
from meridian.indexing.parent_child import ChunkRecord
from meridian.indexing.store import IndexStore


def _record(text: str) -> list[ChunkRecord]:
    return [ChunkRecord(text=text, parent_text=text, position=0, is_own_parent=True)]


def _embedding() -> list[np.ndarray]:
    return [np.zeros(4, dtype=np.float32)]


def test_search_finds_matching_chunk(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    store.upsert_item_chunks("gmail", "msg-1", _record("the quarterly budget report"), _embedding(), {})
    store.upsert_item_chunks("gmail", "msg-2", _record("dinner plans for friday"), _embedding(), {})

    results = search(store, "budget", k=5)

    assert len(results) == 1
    assert results[0][0] == "gmail:msg-1:0000"


def test_search_filters_by_source(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    store.upsert_item_chunks("gmail", "msg-1", _record("shared keyword here"), _embedding(), {})
    store.upsert_item_chunks("docs", "doc-1", _record("shared keyword here"), _embedding(), {})

    results = search(store, "keyword", k=5, source="docs")

    assert len(results) == 1
    assert results[0][0] == "docs:doc-1:0000"


def test_search_empty_query_returns_empty_list(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    store.upsert_item_chunks("gmail", "msg-1", _record("some content"), _embedding(), {})

    assert search(store, "", k=5) == []
    assert search(store, "   ", k=5) == []


def test_search_no_matches_returns_empty_list(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    store.upsert_item_chunks("gmail", "msg-1", _record("some content"), _embedding(), {})

    assert search(store, "nonexistentterm", k=5) == []


def test_search_respects_k_limit(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    for i in range(5):
        store.upsert_item_chunks("gmail", f"msg-{i}", _record("repeated matching term"), _embedding(), {})

    results = search(store, "matching", k=3)

    assert len(results) == 3


def test_search_handles_natural_language_query_with_punctuation(tmp_path):
    # regression test: a raw "?" or other punctuation used to crash fts5's
    # own query-expression parser with a syntax error.
    store = IndexStore(tmp_path / "index.db")
    store.upsert_item_chunks(
        "gmail", "msg-1", _record("the quarterly budget numbers"), _embedding(), {}
    )

    results = search(store, "What did we say about the budget?", k=5)

    assert len(results) == 1
    assert results[0][0] == "gmail:msg-1:0000"


def test_search_punctuation_only_query_returns_empty_list(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    store.upsert_item_chunks("gmail", "msg-1", _record("some content"), _embedding(), {})

    assert search(store, "???", k=5) == []


def test_search_ranks_denser_match_higher(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    store.upsert_item_chunks(
        "gmail", "msg-1", _record("budget budget budget planning"), _embedding(), {}
    )
    store.upsert_item_chunks(
        "gmail", "msg-2", _record("a brief mention of budget somewhere"), _embedding(), {}
    )

    results = search(store, "budget", k=5)

    assert results[0][0] == "gmail:msg-1:0000"
