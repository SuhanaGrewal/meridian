from meridian.conversation.store import ConversationStore


def test_add_turn_and_list_turns(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")

    store.add_turn("t1", "user", "what's on my calendar this week")
    store.add_turn("t1", "assistant", "You have a meeting on Tuesday.")

    turns = store.list_turns("t1")
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "what's on my calendar this week"
    assert turns[1]["role"] == "assistant"


def test_list_turns_is_scoped_per_conversation(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    store.add_turn("t1", "user", "question in thread 1")
    store.add_turn("t2", "user", "question in thread 2")

    assert len(store.list_turns("t1")) == 1
    assert len(store.list_turns("t2")) == 1


def test_list_turns_orders_oldest_first(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    store.add_turn("t1", "user", "first")
    store.add_turn("t1", "assistant", "second")
    store.add_turn("t1", "user", "third")

    turns = store.list_turns("t1")

    assert [t["content"] for t in turns] == ["first", "second", "third"]


def test_list_turns_respects_limit_keeping_most_recent(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    for i in range(5):
        store.add_turn("t1", "user", f"turn {i}")

    turns = store.list_turns("t1", limit=2)

    assert [t["content"] for t in turns] == ["turn 3", "turn 4"]


def test_list_turns_unknown_conversation_returns_empty(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")

    assert store.list_turns("does-not-exist") == []


def test_clear_conversation_removes_only_that_thread(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    store.add_turn("t1", "user", "keep me")
    store.add_turn("t2", "user", "delete me")

    store.clear_conversation("t2")

    assert len(store.list_turns("t1")) == 1
    assert store.list_turns("t2") == []


def test_count_turns(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    store.add_turn("t1", "user", "a")
    store.add_turn("t1", "assistant", "b")
    store.add_turn("t2", "user", "c")

    assert store.count_turns() == 3
    assert store.count_turns("t1") == 2
