import numpy as np

from meridian.entity_graph.store import EntityGraphStore
from meridian.entity_graph.topic_graph import link_item_to_topic


class _FakeAnalyzer:
    def analyze(self, text, entities, language):
        return []


class _FakeMessages:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._replies.pop(0))


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeClient:
    def __init__(self, replies):
        self.messages = _FakeMessages(replies)


def test_link_item_to_topic_creates_new_topic_when_none_exist(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    client = _FakeClient(["Q3 budget planning"])

    topic_id = link_item_to_topic(
        "gmail", "msg-1", "Let's finalize the Q3 budget", np.array([1.0, 0.0, 0.0], dtype=np.float32),
        store, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(),
    )

    assert store.get_topic(topic_id)["label"] == "Q3 budget planning"
    assert store.nodes_related_via("item:gmail:msg-1", "about_topic") == [f"topic:{topic_id}"]


def test_link_item_to_topic_reuses_existing_similar_topic_without_calling_llm(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.add_topic("topic-1", "Q3 budget planning", np.array([1.0, 0.0, 0.0], dtype=np.float32))
    client = _FakeClient([])  # any .create() call would raise IndexError - proves no LLM call happens

    topic_id = link_item_to_topic(
        "calendar", "evt-1", "Budget review meeting", np.array([1.0, 0.0, 0.0], dtype=np.float32),
        store, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(),
    )

    assert topic_id == "topic-1"
    assert store.nodes_related_via("item:calendar:evt-1", "about_topic") == ["topic:topic-1"]


def test_link_item_to_topic_mints_new_topic_when_dissimilar(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.add_topic("topic-1", "Q3 budget planning", np.array([1.0, 0.0, 0.0], dtype=np.float32))
    client = _FakeClient(["Team offsite logistics"])

    topic_id = link_item_to_topic(
        "gmail", "msg-2", "Where should we host the offsite?", np.array([0.0, 1.0, 0.0], dtype=np.float32),
        store, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(),
    )

    assert topic_id != "topic-1"
    assert store.count_topics() == 2


def test_link_item_to_topic_two_items_about_same_subject_are_traversable(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    client = _FakeClient(["Q3 budget planning"])

    topic_id = link_item_to_topic(
        "gmail", "msg-1", "Let's finalize the Q3 budget", np.array([1.0, 0.0, 0.0], dtype=np.float32),
        store, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(),
    )
    link_item_to_topic(
        "calendar", "evt-1", "Budget finalization meeting", np.array([1.0, 0.0, 0.0], dtype=np.float32),
        store, client=_FakeClient([]), model="claude-haiku-4-5", analyzer=_FakeAnalyzer(),
    )

    assert store.items_sharing_topic_with("gmail", "msg-1") == [("calendar", "evt-1")]
    assert topic_id is not None
