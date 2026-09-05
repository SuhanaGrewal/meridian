from datetime import datetime, timezone

import numpy as np

from meridian.entity_graph.store import EntityGraphStore


def test_upsert_entity_creates_new_entity(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")

    created = store.upsert_entity("PERSON:email:jane@example.com", "PERSON", "email:jane@example.com", "Jane Doe", "jane@example.com")

    assert created is True
    row = store.get_entity("PERSON:email:jane@example.com")
    assert row["display_name"] == "Jane Doe"
    assert row["email"] == "jane@example.com"


def test_upsert_entity_existing_returns_false_and_updates_display_name(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.upsert_entity("PERSON:email:jane@example.com", "PERSON", "email:jane@example.com", "Jane", "jane@example.com")

    created = store.upsert_entity("PERSON:email:jane@example.com", "PERSON", "email:jane@example.com", "Jane Doe", "jane@example.com")

    assert created is False
    assert store.get_entity("PERSON:email:jane@example.com")["display_name"] == "Jane Doe"


def test_upsert_entity_never_erases_a_known_email(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.upsert_entity("PERSON:email:jane@example.com", "PERSON", "email:jane@example.com", "Jane Doe", "jane@example.com")

    store.upsert_entity("PERSON:email:jane@example.com", "PERSON", "email:jane@example.com", "Jane Doe", None)

    assert store.get_entity("PERSON:email:jane@example.com")["email"] == "jane@example.com"


def test_list_person_entities_with_email_excludes_name_only_and_non_person(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.upsert_entity("PERSON:email:jane@example.com", "PERSON", "email:jane@example.com", "Jane Doe", "jane@example.com")
    store.upsert_entity("PERSON:name:john smith", "PERSON", "name:john smith", "John Smith", None)
    store.upsert_entity("ORG:name:acme corp", "ORG", "name:acme corp", "Acme Corp", None)

    rows = store.list_person_entities_with_email()

    assert len(rows) == 1
    assert rows[0]["entity_id"] == "PERSON:email:jane@example.com"


def test_add_mention_and_count_mentions(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.upsert_entity("PERSON:email:jane@example.com", "PERSON", "email:jane@example.com", "Jane Doe", "jane@example.com")

    store.add_mention("PERSON:email:jane@example.com", "gmail", "msg-1", None, "Jane Doe <jane@example.com>", "structured")
    store.add_mention("PERSON:email:jane@example.com", "calendar", "cal:evt-1", None, "jane@example.com", "structured")

    assert store.count_mentions() == 2
    assert store.count_mentions("structured") == 2
    assert store.count_mentions("ner") == 0


def test_delete_mentions_for_item_scoped_to_kind(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.upsert_entity("PERSON:name:jane doe", "PERSON", "name:jane doe", "Jane Doe", None)
    store.add_mention("PERSON:name:jane doe", "gmail", "msg-1", "gmail:msg-1:0000", "Jane Doe", "ner")
    store.add_mention("PERSON:name:jane doe", "gmail", "msg-1", None, "Jane Doe <jane@example.com>", "structured")

    store.delete_mentions_for_item("gmail", "msg-1", "ner")

    assert store.count_mentions("ner") == 0
    assert store.count_mentions("structured") == 1


def test_change_signal_tracking_is_scoped_by_phase(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")

    assert store.get_change_signal("gmail", "msg-1", "structured") is None
    assert store.get_change_signal("gmail", "msg-1", "ner") is None

    store.set_processed("gmail", "msg-1", "structured", "hash-1")

    assert store.get_change_signal("gmail", "msg-1", "structured") == "hash-1"
    # same (source, source_item_id) but a different phase is untouched -
    # this is the correctness property the "phase" column exists for.
    assert store.get_change_signal("gmail", "msg-1", "ner") is None


def test_set_processed_updates_existing_signal(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.set_processed("gmail", "msg-1", "structured", "hash-1")

    store.set_processed("gmail", "msg-1", "structured", "hash-2")

    assert store.get_change_signal("gmail", "msg-1", "structured") == "hash-2"


def test_get_processed_item_ids_scoped_by_source_and_phase(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.set_processed("gmail", "msg-1", "structured", "hash-1")
    store.set_processed("gmail", "msg-2", "ner", "hash-2")
    store.set_processed("calendar", "cal:evt-1", "structured", "hash-3")

    assert store.get_processed_item_ids("gmail", "structured") == {"msg-1"}
    assert store.get_processed_item_ids("gmail", "ner") == {"msg-2"}
    assert store.get_processed_item_ids("calendar", "structured") == {"cal:evt-1"}


def test_clear_processed_removes_only_that_phase(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.set_processed("gmail", "msg-1", "structured", "hash-1")
    store.set_processed("gmail", "msg-1", "ner", "hash-2")

    store.clear_processed("gmail", "msg-1", "structured")

    assert store.get_change_signal("gmail", "msg-1", "structured") is None
    assert store.get_change_signal("gmail", "msg-1", "ner") == "hash-2"


def test_count_entities_by_type(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.upsert_entity("PERSON:email:jane@example.com", "PERSON", "email:jane@example.com", "Jane Doe", "jane@example.com")
    store.upsert_entity("ORG:name:acme corp", "ORG", "name:acme corp", "Acme Corp", None)

    assert store.count_entities() == 2
    assert store.count_entities("PERSON") == 1
    assert store.count_entities("ORG") == 1
    assert store.count_entities("GPE") == 0


def test_count_cross_source_entities(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.upsert_entity("PERSON:email:jane@example.com", "PERSON", "email:jane@example.com", "Jane Doe", "jane@example.com")
    store.upsert_entity("PERSON:email:bob@example.com", "PERSON", "email:bob@example.com", "Bob", "bob@example.com")

    store.add_mention("PERSON:email:jane@example.com", "gmail", "msg-1", None, "Jane Doe", "structured")
    store.add_mention("PERSON:email:jane@example.com", "calendar", "cal:evt-1", None, "jane@example.com", "structured")
    store.add_mention("PERSON:email:bob@example.com", "gmail", "msg-2", None, "Bob", "structured")

    assert store.count_cross_source_entities() == 1


def test_list_entities_mentioned_since_excludes_mentions_before_cutoff(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.upsert_entity("PERSON:name:old person", "PERSON", "name:old person", "Old Person")
    store.add_mention("PERSON:name:old person", "gmail", "msg-1", None, "Old Person", "ner")

    cutoff = datetime.now(tz=timezone.utc).isoformat()

    store.upsert_entity("PERSON:name:new person", "PERSON", "name:new person", "New Person")
    store.add_mention("PERSON:name:new person", "gmail", "msg-2", None, "New Person", "ner")

    rows = store.list_entities_mentioned_since(cutoff)

    assert {row["entity_id"] for row in rows} == {"PERSON:name:new person"}


def test_list_entities_mentioned_since_orders_by_mention_count_desc(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    cutoff = datetime.now(tz=timezone.utc).isoformat()
    store.upsert_entity("PERSON:name:popular", "PERSON", "name:popular", "Popular")
    store.upsert_entity("PERSON:name:rare", "PERSON", "name:rare", "Rare")
    store.add_mention("PERSON:name:popular", "gmail", "msg-1", None, "Popular", "ner")
    store.add_mention("PERSON:name:popular", "gmail", "msg-2", None, "Popular", "ner")
    store.add_mention("PERSON:name:rare", "gmail", "msg-3", None, "Rare", "ner")

    rows = store.list_entities_mentioned_since(cutoff)

    assert [row["entity_id"] for row in rows] == ["PERSON:name:popular", "PERSON:name:rare"]
    assert rows[0]["mention_count"] == 2


def test_list_entities_mentioned_since_respects_limit(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    cutoff = datetime.now(tz=timezone.utc).isoformat()
    for i in range(3):
        entity_id = f"PERSON:name:person {i}"
        store.upsert_entity(entity_id, "PERSON", f"name:person {i}", f"Person {i}")
        store.add_mention(entity_id, "gmail", f"msg-{i}", None, f"Person {i}", "ner")

    rows = store.list_entities_mentioned_since(cutoff, limit=2)

    assert len(rows) == 2


def test_add_topic_and_get_topic(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")

    store.add_topic("topic-1", "Q3 budget planning", np.array([1.0, 0.0, 0.0], dtype=np.float32))

    row = store.get_topic("topic-1")
    assert row["label"] == "Q3 budget planning"
    assert np.frombuffer(row["embedding"], dtype=np.float32).tolist() == [1.0, 0.0, 0.0]


def test_list_topics_with_embeddings_and_count_topics(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.add_topic("topic-1", "Budget", np.zeros(3, dtype=np.float32))
    store.add_topic("topic-2", "Hiring", np.zeros(3, dtype=np.float32))

    rows = store.list_topics_with_embeddings()

    assert store.count_topics() == 2
    assert {row["topic_id"] for row in rows} == {"topic-1", "topic-2"}


def test_add_graph_edge_is_idempotent(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")

    store.add_graph_edge("item:gmail:msg-1", "topic:topic-1", "about_topic")
    store.add_graph_edge("item:gmail:msg-1", "topic:topic-1", "about_topic")

    assert store.nodes_related_via("item:gmail:msg-1", "about_topic") == ["topic:topic-1"]


def test_items_sharing_topic_with_finds_other_item_via_shared_topic(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.add_graph_edge("item:gmail:msg-1", "topic:topic-1", "about_topic")
    store.add_graph_edge("item:calendar:evt-1", "topic:topic-1", "about_topic")
    store.add_graph_edge("item:gmail:msg-2", "topic:topic-2", "about_topic")

    related = store.items_sharing_topic_with("gmail", "msg-1")

    assert related == [("calendar", "evt-1")]


def test_items_sharing_topic_with_returns_empty_when_item_has_no_topic(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")

    assert store.items_sharing_topic_with("gmail", "msg-unlinked") == []


def test_items_sharing_topic_with_excludes_the_item_itself(tmp_path):
    store = EntityGraphStore(tmp_path / "entity_graph.db")
    store.add_graph_edge("item:gmail:msg-1", "topic:topic-1", "about_topic")

    assert store.items_sharing_topic_with("gmail", "msg-1") == []
