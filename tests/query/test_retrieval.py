from datetime import datetime, timezone

import numpy as np

from meridian.indexing.parent_child import ChunkRecord
from meridian.indexing.store import IndexStore
from meridian.query.retrieval import _fetch_and_filter_candidates


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
