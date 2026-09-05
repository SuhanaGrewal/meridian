from meridian.replies.store import DraftStore


def test_add_draft_and_get_draft(tmp_path):
    store = DraftStore(tmp_path / "drafts.db")

    draft_id = store.add_draft("t1", "m1", "alice@example.com", "Thanks for reaching out!")

    row = store.get_draft(draft_id)
    assert row["thread_id"] == "t1"
    assert row["message_id"] == "m1"
    assert row["recipient_email"] == "alice@example.com"
    assert row["draft_text"] == "Thanks for reaching out!"
    assert row["status"] == "pending"


def test_get_draft_for_thread_returns_most_recent(tmp_path):
    store = DraftStore(tmp_path / "drafts.db")
    store.add_draft("t1", "m1", "alice@example.com", "first draft")
    second_id = store.add_draft("t1", "m2", "alice@example.com", "second draft")

    row = store.get_draft_for_thread("t1")

    assert row["draft_id"] == second_id


def test_update_draft_text(tmp_path):
    store = DraftStore(tmp_path / "drafts.db")
    draft_id = store.add_draft("t1", "m1", "alice@example.com", "original")

    updated = store.update_draft_text(draft_id, "edited text")

    assert updated is True
    assert store.get_draft(draft_id)["draft_text"] == "edited text"


def test_update_draft_text_unknown_id_returns_false(tmp_path):
    store = DraftStore(tmp_path / "drafts.db")

    assert store.update_draft_text("does-not-exist", "x") is False


def test_approve_and_reject(tmp_path):
    store = DraftStore(tmp_path / "drafts.db")
    approve_id = store.add_draft("t1", "m1", "alice@example.com", "draft")
    reject_id = store.add_draft("t2", "m2", "bob@example.com", "draft")

    assert store.approve(approve_id) is True
    assert store.reject(reject_id) is True
    assert store.get_draft(approve_id)["status"] == "approved"
    assert store.get_draft(reject_id)["status"] == "rejected"


def test_list_pending_drafts_excludes_decided(tmp_path):
    store = DraftStore(tmp_path / "drafts.db")
    pending_id = store.add_draft("t1", "m1", "alice@example.com", "draft")
    approved_id = store.add_draft("t2", "m2", "bob@example.com", "draft")
    store.approve(approved_id)

    pending = store.list_pending_drafts()

    assert len(pending) == 1
    assert pending[0]["draft_id"] == pending_id


def test_count_drafts(tmp_path):
    store = DraftStore(tmp_path / "drafts.db")
    store.add_draft("t1", "m1", "alice@example.com", "a")
    store.add_draft("t2", "m2", "bob@example.com", "b")

    assert store.count_drafts() == 2
