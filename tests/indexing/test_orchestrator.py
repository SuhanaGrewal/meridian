import numpy as np

from meridian.indexing.orchestrator import IndexStats, index_source, run_indexing
from meridian.indexing.store import IndexStore
from meridian.ingestion.docs.doc_parser import ParsedDoc
from meridian.ingestion.docs.store import DocsStore
from meridian.ingestion.gmail.message_parser import ParsedMessage
from meridian.ingestion.gmail.store import GmailStore


class _FakeEmbedder:
    def __init__(self, dim: int = 4):
        self.dim = dim
        self.calls = 0

    def encode(self, texts, batch_size=32, show_progress_bar=False):
        self.calls += 1
        return np.array([[float(len(t))] * self.dim for t in texts], dtype=np.float32)


def _message(message_id="msg-1", subject="Hello", body="Body text", content_hash="hash-1") -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id,
        thread_id="thread-1",
        subject=subject,
        sender="alice@example.com",
        recipients=["bob@example.com"],
        sent_at="2024-01-01T00:00:00+00:00",
        body_text=body,
        label_ids=["INBOX"],
        content_hash=content_hash,
    )


def test_index_source_indexes_new_item(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message())
    index_store = IndexStore(tmp_path / "index.db")
    embedder = _FakeEmbedder()

    stats = index_source("gmail", tmp_path / "gmail.db", index_store, embedder)

    assert stats.items_indexed == 1
    assert stats.items_skipped_unchanged == 0
    assert stats.chunks_written >= 1
    assert embedder.calls == 1
    assert index_store.count_chunks("gmail") >= 1


def test_index_source_skips_unchanged_item_on_rerun(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message())
    index_store = IndexStore(tmp_path / "index.db")
    embedder = _FakeEmbedder()
    index_source("gmail", tmp_path / "gmail.db", index_store, embedder)

    stats = index_source("gmail", tmp_path / "gmail.db", index_store, embedder)

    assert stats.items_indexed == 0
    assert stats.items_skipped_unchanged == 1
    assert embedder.calls == 1  # not called again


def test_index_source_reindexes_changed_item(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message(content_hash="hash-1", body="v1"))
    index_store = IndexStore(tmp_path / "index.db")
    embedder = _FakeEmbedder()
    index_source("gmail", tmp_path / "gmail.db", index_store, embedder)

    gmail_store.upsert_message(_message(content_hash="hash-2", body="v2"))
    stats = index_source("gmail", tmp_path / "gmail.db", index_store, embedder)

    assert stats.items_indexed == 1
    assert embedder.calls == 2
    row = index_store.get_chunk_row("gmail:msg-1:0000")
    assert "v2" in row["chunk_text"]


def test_index_source_reconciles_deleted_item(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message(message_id="msg-1"))
    gmail_store.upsert_message(_message(message_id="msg-2"))
    index_store = IndexStore(tmp_path / "index.db")
    embedder = _FakeEmbedder()
    index_source("gmail", tmp_path / "gmail.db", index_store, embedder)

    gmail_store.mark_deleted("msg-2")
    stats = index_source("gmail", tmp_path / "gmail.db", index_store, embedder)

    assert stats.items_deleted == 1
    assert index_store.count_chunks("gmail") == 1
    assert index_store.get_indexed_item_ids("gmail") == {"msg-1"}


def test_index_source_handles_empty_text_item(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message(subject="", body=""))
    index_store = IndexStore(tmp_path / "index.db")
    embedder = _FakeEmbedder()

    stats = index_source("gmail", tmp_path / "gmail.db", index_store, embedder)

    assert stats.items_indexed == 1
    assert index_store.count_chunks("gmail") == 0
    # recorded as indexed so it isn't retried every single run
    assert index_store.get_change_signal("gmail", "msg-1") == "hash-1"


def test_index_source_with_no_ingested_data_returns_empty_stats(tmp_path):
    index_store = IndexStore(tmp_path / "index.db")
    embedder = _FakeEmbedder()

    stats = index_source("gmail", tmp_path / "gmail.db", index_store, embedder)

    assert stats == IndexStats(duration_ms=stats.duration_ms)


def test_run_indexing_covers_all_sources_by_default(tmp_path):
    ingestion_dir = tmp_path / "ingestion"
    gmail_store = GmailStore(ingestion_dir / "gmail" / "gmail.db")
    gmail_store.upsert_message(_message())
    docs_store = DocsStore(ingestion_dir / "docs" / "docs.db")
    docs_store.upsert_document(
        ParsedDoc(doc_id="doc-1", title="Doc", content_text="content", modified_time=None, content_hash="h1")
    )
    index_store = IndexStore(tmp_path / "index.db")
    embedder = _FakeEmbedder()

    results = run_indexing(ingestion_dir, index_store, embedder)

    assert set(results.keys()) == {"gmail", "calendar", "docs", "local_files"}
    assert results["gmail"].items_indexed == 1
    assert results["docs"].items_indexed == 1
    assert results["calendar"].items_indexed == 0  # no calendar.db present
    assert results["local_files"].items_indexed == 0  # no local_files.db present


def test_index_source_force_reprocesses_unchanged_item(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message())
    index_store = IndexStore(tmp_path / "index.db")
    embedder = _FakeEmbedder()
    index_source("gmail", tmp_path / "gmail.db", index_store, embedder)

    stats = index_source("gmail", tmp_path / "gmail.db", index_store, embedder, force=True)

    assert stats.items_indexed == 1
    assert stats.items_skipped_unchanged == 0
    assert embedder.calls == 2


def test_run_indexing_respects_sources_filter(tmp_path):
    ingestion_dir = tmp_path / "ingestion"
    gmail_store = GmailStore(ingestion_dir / "gmail" / "gmail.db")
    gmail_store.upsert_message(_message())
    index_store = IndexStore(tmp_path / "index.db")
    embedder = _FakeEmbedder()

    results = run_indexing(ingestion_dir, index_store, embedder, sources=["gmail"])

    assert set(results.keys()) == {"gmail"}
