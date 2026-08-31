from meridian.ingestion.docs.doc_parser import ParsedDoc
from meridian.ingestion.docs.store import DocsStore
from meridian.ingestion.docs.sync import SyncStats, _fetch_and_store


class _Request:
    def __init__(self, result):
        self._result = result

    def execute(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _QueuedRequest:
    """mimics retrying the *same* request object's .execute() across attempts."""

    def __init__(self, outcomes: list):
        self._outcomes = outcomes

    def execute(self):
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeDocuments:
    def __init__(self, get_responses):
        self._get_responses = {
            key: (list(value) if isinstance(value, list) else [value])
            for key, value in (get_responses or {}).items()
        }

    def get(self, **kwargs):
        return _QueuedRequest(self._get_responses[kwargs["documentId"]])


class _FakeDocsService:
    def __init__(self, *, get_responses=None):
        self.documents_double = _FakeDocuments(get_responses or {})

    def documents(self):
        return self.documents_double


def _raw_document(doc_id: str, title: str = "Title", text: str = "Body") -> dict:
    return {
        "documentId": doc_id,
        "title": title,
        "body": {"content": [{"paragraph": {"elements": [{"textRun": {"content": text + "\n"}}]}}]},
    }


def test_fetch_and_store_fetches_and_upserts_new_document(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    stats = SyncStats(sync_type="full")
    docs_service = _FakeDocsService(get_responses={"doc-1": _raw_document("doc-1")})

    _fetch_and_store(
        docs_service,
        store,
        {"id": "doc-1", "modifiedTime": "2024-01-01T00:00:00Z", "trashed": False},
        stats,
    )

    assert stats.documents_fetched == 1
    assert store.count_documents() == 1


def test_fetch_and_store_marks_trashed_file_without_fetching(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(
        ParsedDoc(doc_id="doc-1", title="T", content_text="C", modified_time="x", content_hash="h")
    )
    stats = SyncStats(sync_type="incremental")
    docs_service = _FakeDocsService()

    _fetch_and_store(docs_service, store, {"id": "doc-1", "trashed": True}, stats)

    assert stats.documents_trashed == 1
    assert store.get_document_row("doc-1")["is_trashed"] == 1


def test_fetch_and_store_skips_unchanged_document(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(
        ParsedDoc(
            doc_id="doc-1",
            title="T",
            content_text="C",
            modified_time="2024-01-01T00:00:00Z",
            content_hash="h",
        )
    )
    stats = SyncStats(sync_type="incremental")
    docs_service = _FakeDocsService()

    _fetch_and_store(
        docs_service,
        store,
        {"id": "doc-1", "modifiedTime": "2024-01-01T00:00:00Z", "trashed": False},
        stats,
    )

    assert stats.documents_skipped_unchanged == 1
    assert stats.documents_fetched == 0


def test_fetch_and_store_dead_letters_malformed_document(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    stats = SyncStats(sync_type="full")
    docs_service = _FakeDocsService(get_responses={"doc-1": {"title": "no id"}})

    _fetch_and_store(
        docs_service,
        store,
        {"id": "doc-1", "modifiedTime": "x", "trashed": False},
        stats,
    )

    assert stats.parse_failures == 1
    assert store.count_documents() == 0


def test_fetch_and_store_handles_missing_file_id(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    stats = SyncStats(sync_type="full")
    docs_service = _FakeDocsService()

    _fetch_and_store(docs_service, store, {"name": "mystery"}, stats)

    assert stats.parse_failures == 1
