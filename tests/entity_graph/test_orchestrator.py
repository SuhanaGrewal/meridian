import numpy as np

from meridian.entity_graph.orchestrator import run_extraction
from meridian.entity_graph.store import EntityGraphStore
from meridian.indexing.parent_child import ChunkRecord
from meridian.indexing.store import IndexStore
from meridian.ingestion.calendar.event_parser import ParsedEvent
from meridian.ingestion.calendar.store import CalendarStore
from meridian.ingestion.gmail.message_parser import ParsedMessage
from meridian.ingestion.gmail.store import GmailStore


class _FakeSpan:
    def __init__(self, text, label):
        self.text = text
        self.label_ = label
        self.start_char = 0
        self.end_char = len(text)


class _FakeDoc:
    def __init__(self, ents):
        self.ents = ents


class _FakeNlp:
    """returns canned entities keyed by exact input text; raises for any
    text listed in raise_for_texts."""

    def __init__(self, entities_by_text=None, raise_for_texts=None):
        self.entities_by_text = entities_by_text or {}
        self.raise_for_texts = raise_for_texts or set()
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)
        if text in self.raise_for_texts:
            raise ValueError("simulated NER failure")
        ents = self.entities_by_text.get(text, [])
        return _FakeDoc([_FakeSpan(t, label) for t, label in ents])


def _message(message_id="msg-1", sender="Jane Doe <jane@example.com>", recipients=None) -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id,
        thread_id="thread-1",
        subject="Subject",
        sender=sender,
        recipients=recipients or [],
        sent_at="2024-01-01T00:00:00+00:00",
        body_text="hello",
        label_ids=["INBOX"],
        content_hash=f"hash-{message_id}",
    )


def _event(
    event_id="evt-1", organizer_email="jane@example.com", attendees=None
) -> ParsedEvent:
    return ParsedEvent(
        calendar_id="primary",
        event_id=event_id,
        ical_uid=f"{event_id}@google.com",
        recurring_event_id=None,
        summary="Budget meeting",
        description="",
        location="",
        status="confirmed",
        start_at="2024-06-01T10:00:00-05:00",
        end_at="2024-06-01T10:30:00-05:00",
        is_all_day=False,
        organizer_email=organizer_email,
        attendees=attendees or [],
        source_updated_at=f"2024-05-01T00:00:00.000Z-{event_id}",
    )


def _seed_doc_chunk(index_store, doc_id, text):
    index_store.upsert_item_chunks(
        "docs",
        doc_id,
        [ChunkRecord(text=text, parent_text=text, position=0, is_own_parent=True)],
        [np.zeros(4, dtype=np.float32)],
        {"title": doc_id},
    )


def test_email_seen_as_both_gmail_sender_and_calendar_attendee_links_to_one_entity(tmp_path):
    ingestion_dir = tmp_path / "ingestion"
    GmailStore(ingestion_dir / "gmail" / "gmail.db").upsert_message(_message())
    CalendarStore(ingestion_dir / "calendar" / "calendar.db").upsert_event(
        _event(attendees=[{"email": "jane@example.com", "display_name": "Jane Doe", "response_status": "accepted"}])
    )
    index_store = IndexStore(tmp_path / "index.db")
    entity_store = EntityGraphStore(tmp_path / "entity_graph.db")

    run_extraction(ingestion_dir, index_store, entity_store, _FakeNlp(), sources=["gmail", "calendar"])

    assert entity_store.count_cross_source_entities() == 1
    entity = entity_store.get_entity("PERSON:email:jane@example.com")
    assert entity is not None
    assert entity_store.count_entities("PERSON") == 1


def test_name_only_ner_mention_links_to_existing_email_backed_entity(tmp_path):
    ingestion_dir = tmp_path / "ingestion"
    GmailStore(ingestion_dir / "gmail" / "gmail.db").upsert_message(_message())
    index_store = IndexStore(tmp_path / "index.db")
    _seed_doc_chunk(index_store, "doc-1", "Jane Doe presented the roadmap.")
    entity_store = EntityGraphStore(tmp_path / "entity_graph.db")
    nlp = _FakeNlp(entities_by_text={"Jane Doe presented the roadmap.": [("Jane Doe", "PERSON")]})

    run_extraction(ingestion_dir, index_store, entity_store, nlp, sources=["gmail", "docs"])

    assert entity_store.count_entities("PERSON") == 1
    assert entity_store.count_cross_source_entities() == 1
    entity = entity_store.get_entity("PERSON:email:jane@example.com")
    assert entity is not None


def test_unrelated_ner_found_name_creates_a_new_separate_entity(tmp_path):
    ingestion_dir = tmp_path / "ingestion"
    GmailStore(ingestion_dir / "gmail" / "gmail.db").upsert_message(_message())
    index_store = IndexStore(tmp_path / "index.db")
    _seed_doc_chunk(index_store, "doc-1", "Bob Nobody wrote this note.")
    entity_store = EntityGraphStore(tmp_path / "entity_graph.db")
    nlp = _FakeNlp(entities_by_text={"Bob Nobody wrote this note.": [("Bob Nobody", "PERSON")]})

    run_extraction(ingestion_dir, index_store, entity_store, nlp, sources=["gmail", "docs"])

    assert entity_store.count_entities("PERSON") == 2
    assert entity_store.count_cross_source_entities() == 0
    bob = entity_store.get_entity("PERSON:name:bob nobody")
    assert bob is not None
    assert bob["email"] is None


def test_org_and_gpe_entities_are_created_from_ner(tmp_path):
    ingestion_dir = tmp_path / "ingestion"
    index_store = IndexStore(tmp_path / "index.db")
    _seed_doc_chunk(index_store, "doc-1", "Acme Corp is based in Paris.")
    entity_store = EntityGraphStore(tmp_path / "entity_graph.db")
    nlp = _FakeNlp(entities_by_text={"Acme Corp is based in Paris.": [("Acme Corp", "ORG"), ("Paris", "GPE")]})

    run_extraction(ingestion_dir, index_store, entity_store, nlp, sources=["docs"])

    assert entity_store.count_entities("ORG") == 1
    assert entity_store.count_entities("GPE") == 1


def test_incremental_rerun_skips_unchanged_items_and_records_no_duplicate_mentions(tmp_path):
    ingestion_dir = tmp_path / "ingestion"
    GmailStore(ingestion_dir / "gmail" / "gmail.db").upsert_message(_message())
    index_store = IndexStore(tmp_path / "index.db")
    _seed_doc_chunk(index_store, "doc-1", "Jane Doe presented the roadmap.")
    entity_store = EntityGraphStore(tmp_path / "entity_graph.db")
    nlp = _FakeNlp(entities_by_text={"Jane Doe presented the roadmap.": [("Jane Doe", "PERSON")]})

    first = run_extraction(ingestion_dir, index_store, entity_store, nlp, sources=["gmail", "docs"])
    mentions_after_first = entity_store.count_mentions()

    second = run_extraction(ingestion_dir, index_store, entity_store, nlp, sources=["gmail", "docs"])

    assert second["gmail"].items_skipped_unchanged == 1
    assert second["docs"].items_skipped_unchanged == 1
    assert second["gmail"].items_processed == 0
    assert second["docs"].items_processed == 0
    assert entity_store.count_mentions() == mentions_after_first
    assert first["gmail"].items_processed == 1
    assert first["docs"].items_processed == 1


def test_force_reextract_reprocesses_unchanged_items(tmp_path):
    ingestion_dir = tmp_path / "ingestion"
    GmailStore(ingestion_dir / "gmail" / "gmail.db").upsert_message(_message())
    index_store = IndexStore(tmp_path / "index.db")
    entity_store = EntityGraphStore(tmp_path / "entity_graph.db")
    nlp = _FakeNlp()

    run_extraction(ingestion_dir, index_store, entity_store, nlp, sources=["gmail"])
    second = run_extraction(ingestion_dir, index_store, entity_store, nlp, sources=["gmail"], force=True)

    assert second["gmail"].items_processed == 1
    assert second["gmail"].items_skipped_unchanged == 0


def test_a_chunk_that_makes_ner_raise_does_not_crash_the_run(tmp_path):
    ingestion_dir = tmp_path / "ingestion"
    index_store = IndexStore(tmp_path / "index.db")
    _seed_doc_chunk(index_store, "doc-bad", "this chunk breaks ner")
    _seed_doc_chunk(index_store, "doc-good", "Jane Doe presented the roadmap.")
    entity_store = EntityGraphStore(tmp_path / "entity_graph.db")
    nlp = _FakeNlp(
        entities_by_text={"Jane Doe presented the roadmap.": [("Jane Doe", "PERSON")]},
        raise_for_texts={"this chunk breaks ner"},
    )

    results = run_extraction(ingestion_dir, index_store, entity_store, nlp, sources=["docs"])

    assert results["docs"].chunks_failed == 1
    assert results["docs"].items_processed == 2
    assert entity_store.count_entities("PERSON") == 1


def test_stale_gmail_message_deleted_upstream_is_reconciled(tmp_path):
    ingestion_dir = tmp_path / "ingestion"
    gmail_store = GmailStore(ingestion_dir / "gmail" / "gmail.db")
    gmail_store.upsert_message(_message(message_id="msg-1"))
    index_store = IndexStore(tmp_path / "index.db")
    entity_store = EntityGraphStore(tmp_path / "entity_graph.db")
    nlp = _FakeNlp()

    run_extraction(ingestion_dir, index_store, entity_store, nlp, sources=["gmail"])
    assert entity_store.count_mentions("structured") == 1

    gmail_store.mark_deleted("msg-1")
    results = run_extraction(ingestion_dir, index_store, entity_store, nlp, sources=["gmail"])

    assert results["gmail"].items_deleted == 1
    assert entity_store.count_mentions("structured") == 0
