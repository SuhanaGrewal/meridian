import json

import httplib2
import pytest
from googleapiclient.errors import HttpError

from meridian.ingestion.docs.doc_parser import ParsedDoc
from meridian.ingestion.docs.store import DocsStore
from meridian.ingestion.docs.sync import (
    SyncStats,
    _ChangesTokenInvalid,
    _fetch_and_store,
    _full_backfill,
    _incremental_sync,
    run_sync,
)


def _http_error(status: int, *, retry_after: str | None = None, reason: str | None = None) -> HttpError:
    headers = {"status": str(status)}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    resp = httplib2.Response(headers)
    errors = [{"reason": reason}] if reason else []
    content = json.dumps({"error": {"errors": errors}}).encode("utf-8")
    return HttpError(resp, content)


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


class _FakeFiles:
    def __init__(self, list_pages, call_log=None):
        self._list_pages = [(page if isinstance(page, list) else [page]) for page in list_pages]
        self.list_calls = []
        self._call_log = call_log

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        if self._call_log is not None:
            self._call_log.append("files.list")
        outcomes = self._list_pages.pop(0)
        return _QueuedRequest(outcomes) if len(outcomes) > 1 else _Request(outcomes[0])


class _FakeChanges:
    def __init__(self, start_token_outcomes=None, list_pages=None, call_log=None):
        self._start_token_outcomes = list(start_token_outcomes or [{"startPageToken": "start-1"}])
        self._list_pages = [(page if isinstance(page, list) else [page]) for page in (list_pages or [])]
        self.list_calls = []
        self._call_log = call_log

    def getStartPageToken(self, **kwargs):
        if self._call_log is not None:
            self._call_log.append("getStartPageToken")
        if len(self._start_token_outcomes) > 1:
            return _QueuedRequest(self._start_token_outcomes)
        return _Request(self._start_token_outcomes[0])

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        if self._call_log is not None:
            self._call_log.append("changes.list")
        outcomes = self._list_pages.pop(0)
        return _QueuedRequest(outcomes) if len(outcomes) > 1 else _Request(outcomes[0])


class _FakeDriveService:
    def __init__(
        self, *, start_token_outcomes=None, files_list_pages=None, changes_list_pages=None
    ):
        self.call_log: list[str] = []
        self.files_double = _FakeFiles(files_list_pages or [], call_log=self.call_log)
        self.changes_double = _FakeChanges(
            start_token_outcomes=start_token_outcomes,
            list_pages=changes_list_pages,
            call_log=self.call_log,
        )

    def files(self):
        return self.files_double

    def changes(self):
        return self.changes_double


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


def test_full_backfill_stores_documents_and_persists_start_token(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    drive_service = _FakeDriveService(
        start_token_outcomes=[{"startPageToken": "start-1"}],
        files_list_pages=[
            {"files": [{"id": "doc-1", "modifiedTime": "2024-01-01T00:00:00Z", "trashed": False}]}
        ],
    )
    docs_service = _FakeDocsService(get_responses={"doc-1": _raw_document("doc-1")})

    stats = _full_backfill(drive_service, docs_service, store)

    assert stats.sync_type == "full"
    assert stats.documents_fetched == 1
    assert store.get_sync_state().page_token == "start-1"


def test_full_backfill_calls_get_start_page_token_before_listing(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    drive_service = _FakeDriveService(files_list_pages=[{"files": []}])
    docs_service = _FakeDocsService()

    _full_backfill(drive_service, docs_service, store)

    assert drive_service.call_log == ["getStartPageToken", "files.list"]


def test_full_backfill_paginates_across_multiple_pages(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    drive_service = _FakeDriveService(
        files_list_pages=[
            {"files": [{"id": "doc-1", "modifiedTime": "t1", "trashed": False}], "nextPageToken": "p2"},
            {"files": [{"id": "doc-2", "modifiedTime": "t2", "trashed": False}]},
        ]
    )
    docs_service = _FakeDocsService(
        get_responses={"doc-1": _raw_document("doc-1"), "doc-2": _raw_document("doc-2")}
    )

    stats = _full_backfill(drive_service, docs_service, store)

    assert stats.documents_fetched == 2
    assert store.count_documents() == 2


def test_full_backfill_passes_extra_drive_query(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    drive_service = _FakeDriveService(files_list_pages=[{"files": []}])
    docs_service = _FakeDocsService()

    _full_backfill(drive_service, docs_service, store, drive_query="'folder-1' in parents")

    query = drive_service.files_double.list_calls[0]["q"]
    assert "mimeType='application/vnd.google-apps.document'" in query
    assert "'folder-1' in parents" in query


def test_full_backfill_is_idempotent_when_rerun(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    file_meta = {"id": "doc-1", "modifiedTime": "2024-01-01T00:00:00Z", "trashed": False}
    raw_doc = _raw_document("doc-1")

    drive_one = _FakeDriveService(files_list_pages=[{"files": [dict(file_meta)]}])
    docs_one = _FakeDocsService(get_responses={"doc-1": raw_doc})
    _full_backfill(drive_one, docs_one, store)

    drive_two = _FakeDriveService(files_list_pages=[{"files": [dict(file_meta)]}])
    docs_two = _FakeDocsService(get_responses={"doc-1": raw_doc})
    _full_backfill(drive_two, docs_two, store)

    assert store.count_documents() == 1
    assert store.get_sync_state().page_token == "start-1"


def test_full_backfill_tombstones_document_missing_from_fresh_listing(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(
        ParsedDoc(doc_id="doc-stale", title="T", content_text="C", modified_time="x", content_hash="h")
    )
    drive_service = _FakeDriveService(
        files_list_pages=[{"files": [{"id": "doc-1", "modifiedTime": "t1", "trashed": False}]}]
    )
    docs_service = _FakeDocsService(get_responses={"doc-1": _raw_document("doc-1")})

    stats = _full_backfill(drive_service, docs_service, store)

    assert stats.documents_trashed == 1
    assert store.get_document_row("doc-stale")["is_trashed"] == 1


def _doc_change(doc_id: str, **overrides) -> dict:
    file_meta = {
        "id": doc_id,
        "name": f"Doc {doc_id}",
        "mimeType": "application/vnd.google-apps.document",
        "modifiedTime": "2024-01-01T00:00:00Z",
        "trashed": False,
    }
    file_meta.update(overrides)
    return {"fileId": doc_id, "removed": False, "file": file_meta}


def test_incremental_sync_uses_stored_page_token(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    drive_service = _FakeDriveService(
        changes_list_pages=[{"changes": [], "newStartPageToken": "token-2"}]
    )
    docs_service = _FakeDocsService()

    stats = _incremental_sync(drive_service, docs_service, store, page_token="token-1")

    assert stats.sync_type == "incremental"
    assert drive_service.changes_double.list_calls[0]["pageToken"] == "token-1"
    assert store.get_sync_state().page_token == "token-2"


def test_incremental_sync_fetches_doc_mimetype_and_ignores_others(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    non_doc_change = _doc_change("file-1", mimeType="application/vnd.google-apps.spreadsheet")
    doc_change = _doc_change("doc-1")
    drive_service = _FakeDriveService(
        changes_list_pages=[{"changes": [non_doc_change, doc_change], "newStartPageToken": "token-2"}]
    )
    docs_service = _FakeDocsService(get_responses={"doc-1": _raw_document("doc-1")})

    stats = _incremental_sync(drive_service, docs_service, store, page_token="token-1")

    assert stats.documents_fetched == 1
    assert store.count_documents() == 1


def test_incremental_sync_removed_change_tombstones_by_file_id_alone(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(
        ParsedDoc(doc_id="doc-1", title="T", content_text="C", modified_time="x", content_hash="h")
    )
    drive_service = _FakeDriveService(
        changes_list_pages=[
            {"changes": [{"fileId": "doc-1", "removed": True}], "newStartPageToken": "token-2"}
        ]
    )
    docs_service = _FakeDocsService()

    stats = _incremental_sync(drive_service, docs_service, store, page_token="token-1")

    assert stats.documents_trashed == 1
    assert store.get_document_row("doc-1")["is_trashed"] == 1


def test_incremental_sync_trashed_file_tombstones_using_file_object(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(
        ParsedDoc(doc_id="doc-1", title="T", content_text="C", modified_time="x", content_hash="h")
    )
    trashed_change = _doc_change("doc-1", trashed=True)
    drive_service = _FakeDriveService(
        changes_list_pages=[{"changes": [trashed_change], "newStartPageToken": "token-2"}]
    )
    docs_service = _FakeDocsService()

    stats = _incremental_sync(drive_service, docs_service, store, page_token="token-1")

    assert stats.documents_trashed == 1
    assert store.get_document_row("doc-1")["is_trashed"] == 1


def test_incremental_sync_paginates_across_multiple_pages(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    drive_service = _FakeDriveService(
        changes_list_pages=[
            {"changes": [_doc_change("doc-1")], "nextPageToken": "p2"},
            {"changes": [_doc_change("doc-2")], "newStartPageToken": "token-2"},
        ]
    )
    docs_service = _FakeDocsService(
        get_responses={"doc-1": _raw_document("doc-1"), "doc-2": _raw_document("doc-2")}
    )

    stats = _incremental_sync(drive_service, docs_service, store, page_token="token-1")

    assert stats.documents_fetched == 2
    assert store.get_sync_state().page_token == "token-2"


def test_incremental_sync_known_doc_reappearing_as_non_doc_is_tombstoned(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.upsert_document(
        ParsedDoc(doc_id="doc-1", title="T", content_text="C", modified_time="x", content_hash="h")
    )
    change = _doc_change("doc-1", mimeType="application/vnd.google-apps.spreadsheet")
    drive_service = _FakeDriveService(
        changes_list_pages=[{"changes": [change], "newStartPageToken": "token-2"}]
    )
    docs_service = _FakeDocsService()

    stats = _incremental_sync(drive_service, docs_service, store, page_token="token-1")

    assert stats.documents_trashed == 1
    assert store.get_document_row("doc-1")["is_trashed"] == 1


def test_incremental_sync_invalid_token_raises_changes_token_invalid(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    drive_service = _FakeDriveService(changes_list_pages=[_http_error(400)])
    docs_service = _FakeDocsService()

    with pytest.raises(_ChangesTokenInvalid):
        _incremental_sync(drive_service, docs_service, store, page_token="token-1")


def test_incremental_sync_permanent_error_propagates(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    drive_service = _FakeDriveService(
        changes_list_pages=[_http_error(403, reason="insufficientPermissions")]
    )
    docs_service = _FakeDocsService()

    with pytest.raises(HttpError):
        _incremental_sync(drive_service, docs_service, store, page_token="token-1")


def test_incremental_sync_rate_limited_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr("meridian.common.google_api.time.sleep", lambda s: None)
    monkeypatch.setattr("meridian.common.retry.time.sleep", lambda s: None)

    store = DocsStore(tmp_path / "docs.db")
    drive_service = _FakeDriveService(
        changes_list_pages=[
            [_http_error(429, retry_after="1"), {"changes": [], "newStartPageToken": "token-2"}]
        ]
    )
    docs_service = _FakeDocsService()

    stats = _incremental_sync(drive_service, docs_service, store, page_token="token-1")

    assert stats.sync_type == "incremental"
    assert store.get_sync_state().page_token == "token-2"


def test_run_sync_dispatches_to_full_backfill_when_no_page_token(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    drive_service = _FakeDriveService(files_list_pages=[{"files": []}])
    docs_service = _FakeDocsService()

    stats = run_sync(drive_service, docs_service, store)

    assert stats.sync_type == "full"
    assert store.get_sync_state().page_token == "start-1"


def test_run_sync_dispatches_to_incremental_when_page_token_stored(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.set_sync_state("token-1")
    drive_service = _FakeDriveService(
        changes_list_pages=[{"changes": [], "newStartPageToken": "token-2"}]
    )
    docs_service = _FakeDocsService()

    stats = run_sync(drive_service, docs_service, store)

    assert stats.sync_type == "incremental"
    assert drive_service.changes_double.list_calls[0]["pageToken"] == "token-1"


def test_run_sync_falls_back_to_full_resync_on_invalid_token(tmp_path):
    store = DocsStore(tmp_path / "docs.db")
    store.set_sync_state("stale-token")
    drive_service = _FakeDriveService(
        changes_list_pages=[_http_error(400)],
        files_list_pages=[{"files": []}],
    )
    docs_service = _FakeDocsService()

    stats = run_sync(drive_service, docs_service, store)

    assert stats.sync_type == "full"
    assert store.get_sync_state().page_token == "start-1"
