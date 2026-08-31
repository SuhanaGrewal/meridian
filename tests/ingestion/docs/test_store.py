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
