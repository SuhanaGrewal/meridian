from meridian.ingestion.docs.doc_parser import ParsedDoc
from meridian.ingestion.docs.store import DocsStore


def _doc(doc_id="doc-1", title="My Doc", content_text="Hello", modified_time="2024-06-01T00:00:00.000Z") -> ParsedDoc:
    return ParsedDoc(
        doc_id=doc_id,
        title=title,
        content_text=content_text,
        modified_time=modified_time,
        content_hash="hash-1",
    )


def test_store_creates_documents_and_sync_state_tables(tmp_path):
    store = DocsStore(tmp_path / "docs.db")

    tables = {
        row["name"]
        for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    assert "documents" in tables
    assert "sync_state" in tables


def test_upsert_document_then_read_back(tmp_path):
    store = DocsStore(tmp_path / "docs.db")

    store.upsert_document(_doc())

    row = store._conn.execute("SELECT * FROM documents WHERE doc_id = ?", ("doc-1",)).fetchone()
    assert row["title"] == "My Doc"
    assert row["content_text"] == "Hello"
    assert row["modified_time"] == "2024-06-01T00:00:00.000Z"
    assert row["is_trashed"] == 0


def test_upsert_document_twice_with_identical_data_results_in_one_row(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    doc = _doc()

    store.upsert_document(doc)
    store.upsert_document(doc)

    count = store._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    assert count == 1


def test_upsert_document_preserves_fetched_at_but_bumps_updated_at_on_change(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(_doc(content_text="Version 1"))
    first_row = store._conn.execute("SELECT * FROM documents WHERE doc_id = ?", ("doc-1",)).fetchone()

    store.upsert_document(_doc(content_text="Version 2"))
    second_row = store._conn.execute("SELECT * FROM documents WHERE doc_id = ?", ("doc-1",)).fetchone()

    assert second_row["fetched_at"] == first_row["fetched_at"]
    assert second_row["updated_at"] >= first_row["updated_at"]
    assert second_row["content_text"] == "Version 2"


def test_mark_trashed_sets_flag(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(_doc())

    store.mark_trashed("doc-1")

    row = store._conn.execute("SELECT is_trashed FROM documents WHERE doc_id = ?", ("doc-1",)).fetchone()
    assert row["is_trashed"] == 1


def test_get_modified_time_returns_stored_value(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(_doc(modified_time="2024-06-01T00:00:00.000Z"))

    assert store.get_modified_time("doc-1") == "2024-06-01T00:00:00.000Z"


def test_get_modified_time_returns_none_for_unknown_doc(tmp_path):
    store = DocsStore(tmp_path / "docs.db")

    assert store.get_modified_time("unknown-doc") is None


def test_sync_state_round_trip(tmp_path):
    store = DocsStore(tmp_path / "docs.db")

    assert store.get_sync_state().page_token is None

    store.set_sync_state("token-1")
    state = store.get_sync_state()

    assert state.page_token == "token-1"
    assert state.last_synced_at is not None


def test_set_sync_state_overwrites_previous_value(tmp_path):
    store = DocsStore(tmp_path / "docs.db")

    store.set_sync_state("token-1")
    store.set_sync_state("token-2")

    assert store.get_sync_state().page_token == "token-2"


def test_clear_sync_state_resets_to_none(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.set_sync_state("token-1")

    store.clear_sync_state()

    assert store.get_sync_state().page_token is None
