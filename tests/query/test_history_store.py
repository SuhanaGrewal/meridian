from meridian.query.history_store import QueryHistoryStore


def test_add_question_and_get_question(tmp_path):
    store = QueryHistoryStore(tmp_path / "history.db")

    question_id = store.add_question("did I get a reply from Nick", is_waiting=True, asked_at="2024-06-01T00:00:00+00:00")

    row = store.get_question(question_id)
    assert row["question_text"] == "did I get a reply from Nick"
    assert row["is_waiting"] == 1
    assert row["resolved"] == 0
    assert row["asked_at"] == "2024-06-01T00:00:00+00:00"


def test_list_open_waiting_questions_excludes_non_waiting(tmp_path):
    store = QueryHistoryStore(tmp_path / "history.db")
    store.add_question("did I get a reply from Nick", is_waiting=True)
    store.add_question("when is my flight", is_waiting=False)

    rows = store.list_open_waiting_questions()

    assert len(rows) == 1
    assert rows[0]["question_text"] == "did I get a reply from Nick"


def test_mark_resolved_excludes_it_from_open_list(tmp_path):
    store = QueryHistoryStore(tmp_path / "history.db")
    question_id = store.add_question("did I get a reply from Nick", is_waiting=True)

    store.mark_resolved(question_id)

    assert store.list_open_waiting_questions() == []
    row = store.get_question(question_id)
    assert row["resolved"] == 1
    assert row["resolved_at"] is not None


def test_count_questions(tmp_path):
    store = QueryHistoryStore(tmp_path / "history.db")
    store.add_question("q1", is_waiting=True)
    store.add_question("q2", is_waiting=False)

    assert store.count_questions() == 2


def test_list_open_waiting_questions_orders_by_asked_at(tmp_path):
    store = QueryHistoryStore(tmp_path / "history.db")
    store.add_question("later one", is_waiting=True, asked_at="2024-06-02T00:00:00+00:00")
    store.add_question("earlier one", is_waiting=True, asked_at="2024-06-01T00:00:00+00:00")

    rows = store.list_open_waiting_questions()

    assert [row["question_text"] for row in rows] == ["earlier one", "later one"]
