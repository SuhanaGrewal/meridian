import numpy as np

from meridian.indexing.parent_child import ChunkRecord
from meridian.indexing.store import IndexStore


def _records(*texts: str) -> list[ChunkRecord]:
    return [
        ChunkRecord(text=t, parent_text=" ".join(texts), position=i, is_own_parent=len(texts) == 1)
        for i, t in enumerate(texts)
    ]


def _embeddings(n: int, dim: int = 4) -> list[np.ndarray]:
    return [np.full(dim, fill_value=float(i + 1), dtype=np.float32) for i in range(n)]


def test_store_creates_expected_tables(tmp_path):
    store = IndexStore(tmp_path / "index.db")

    tables = {
        row["name"]
        for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
    }

    assert "chunks" in tables
    assert "indexed_items" in tables
    virtual_tables = {
        row["name"] for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%fts5%'")
    }
    assert "chunks_fts" in virtual_tables


def test_upsert_item_chunks_inserts_rows_with_embedding_roundtrip(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    records = _records("hello world", "second chunk")
    embeddings = _embeddings(2)

    store.upsert_item_chunks("gmail", "msg-1", records, embeddings, {"sender": "a@example.com"})

    rows = store._conn.execute(
        "SELECT * FROM chunks WHERE source_item_id = ? ORDER BY position", ("msg-1",)
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["chunk_id"] == "gmail:msg-1:0000"
    assert rows[0]["chunk_text"] == "hello world"
    restored = np.frombuffer(rows[0]["embedding"], dtype=np.float32)
    assert np.array_equal(restored, embeddings[0])


def test_upsert_item_chunks_replaces_previous_chunks_for_same_item(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    store.upsert_item_chunks("gmail", "msg-1", _records("a", "b", "c"), _embeddings(3), {})

    store.upsert_item_chunks("gmail", "msg-1", _records("x"), _embeddings(1), {})

    count = store._conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE source_item_id = ?", ("msg-1",)
    ).fetchone()[0]
    assert count == 1


def test_upsert_item_chunks_keeps_fts_index_in_sync(tmp_path):
    store = IndexStore(tmp_path / "index.db")

    store.upsert_item_chunks("gmail", "msg-1", _records("unique searchable phrase"), _embeddings(1), {})

    matches = store._conn.execute(
        "SELECT chunk_text FROM chunks_fts WHERE chunks_fts MATCH 'searchable'"
    ).fetchall()
    assert len(matches) == 1
    assert matches[0]["chunk_text"] == "unique searchable phrase"


def test_upsert_item_chunks_removes_stale_fts_entries_on_replace(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    store.upsert_item_chunks("gmail", "msg-1", _records("oldwordxyz here"), _embeddings(1), {})

    store.upsert_item_chunks("gmail", "msg-1", _records("newwordabc here"), _embeddings(1), {})

    stale = store._conn.execute(
        "SELECT * FROM chunks_fts WHERE chunks_fts MATCH 'oldwordxyz'"
    ).fetchall()
    assert stale == []


def test_upsert_item_chunks_does_not_affect_other_items(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    store.upsert_item_chunks("gmail", "msg-1", _records("a"), _embeddings(1), {})
    store.upsert_item_chunks("gmail", "msg-2", _records("b"), _embeddings(1), {})

    store.upsert_item_chunks("gmail", "msg-1", _records("a-updated"), _embeddings(1), {})

    count_msg2 = store._conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE source_item_id = ?", ("msg-2",)
    ).fetchone()[0]
    assert count_msg2 == 1
