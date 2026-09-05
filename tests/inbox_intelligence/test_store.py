from meridian.inbox_intelligence.store import InboxIntelligenceStore


def test_is_message_scanned_false_before_marked(tmp_path):
    store = InboxIntelligenceStore(tmp_path / "commitments.db")

    assert store.is_message_scanned("msg-1") is False


def test_mark_message_scanned_roundtrip(tmp_path):
    store = InboxIntelligenceStore(tmp_path / "commitments.db")

    store.mark_message_scanned("msg-1")

    assert store.is_message_scanned("msg-1") is True
    assert store.count_scanned_messages() == 1


def test_mark_message_scanned_twice_is_idempotent(tmp_path):
    store = InboxIntelligenceStore(tmp_path / "commitments.db")

    store.mark_message_scanned("msg-1")
    store.mark_message_scanned("msg-1")

    assert store.count_scanned_messages() == 1


def test_add_commitment_and_list_open(tmp_path):
    store = InboxIntelligenceStore(tmp_path / "commitments.db")

    commitment_id = store.add_commitment(
        message_id="msg-1", thread_id="t-1", made_by="other", other_party="alice@example.com",
        description="Alice will send the report", deadline_phrase="by Friday", due_date="2024-06-14",
    )

    open_commitments = store.list_open_commitments()
    assert len(open_commitments) == 1
    assert open_commitments[0]["commitment_id"] == commitment_id
    assert open_commitments[0]["description"] == "Alice will send the report"
    assert open_commitments[0]["due_date"] == "2024-06-14"
    assert open_commitments[0]["is_resolved"] == 0


def test_mark_resolved_removes_from_open_list(tmp_path):
    store = InboxIntelligenceStore(tmp_path / "commitments.db")
    commitment_id = store.add_commitment(
        message_id="msg-1", thread_id="t-1", made_by="me", other_party="bob@example.com",
        description="I'll send the invoice", deadline_phrase=None, due_date=None,
    )

    result = store.mark_resolved(commitment_id)

    assert result is True
    assert store.list_open_commitments() == []


def test_mark_resolved_unknown_id_returns_false(tmp_path):
    store = InboxIntelligenceStore(tmp_path / "commitments.db")

    assert store.mark_resolved("does-not-exist") is False


def test_list_open_commitments_orders_by_due_date_nulls_last(tmp_path):
    store = InboxIntelligenceStore(tmp_path / "commitments.db")
    store.add_commitment(
        message_id="m1", thread_id="t1", made_by="other", other_party="a@example.com",
        description="no deadline", deadline_phrase=None, due_date=None,
    )
    store.add_commitment(
        message_id="m2", thread_id="t2", made_by="other", other_party="b@example.com",
        description="later deadline", deadline_phrase="next week", due_date="2024-06-20",
    )
    store.add_commitment(
        message_id="m3", thread_id="t3", made_by="other", other_party="c@example.com",
        description="sooner deadline", deadline_phrase="tomorrow", due_date="2024-06-13",
    )

    open_commitments = store.list_open_commitments()

    assert [row["description"] for row in open_commitments] == [
        "sooner deadline", "later deadline", "no deadline",
    ]


def test_is_thread_dismissed_false_before_dismissed(tmp_path):
    store = InboxIntelligenceStore(tmp_path / "commitments.db")

    assert store.is_thread_dismissed("t1") is False


def test_dismiss_thread_roundtrip(tmp_path):
    store = InboxIntelligenceStore(tmp_path / "commitments.db")

    store.dismiss_thread("t1")

    assert store.is_thread_dismissed("t1") is True
    assert store.list_dismissed_thread_ids() == frozenset({"t1"})


def test_dismiss_thread_twice_is_idempotent(tmp_path):
    store = InboxIntelligenceStore(tmp_path / "commitments.db")

    store.dismiss_thread("t1")
    store.dismiss_thread("t1")

    assert store.list_dismissed_thread_ids() == frozenset({"t1"})
