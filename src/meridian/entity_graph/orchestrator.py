from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from meridian.entity_graph.identity import (
    PersonIdentity,
    normalize_text,
    parse_person_header,
    person_entity_id,
    person_identity_key,
    text_entity_id,
    text_identity_key,
)
from meridian.entity_graph.ner import DEFAULT_ENTITY_TYPES, extract_entities
from meridian.entity_graph.store import EntityGraphStore
from meridian.entity_graph.topic_graph import link_item_to_topic
from meridian.indexing.store import IndexStore
from meridian.ingestion.calendar.store import CalendarStore
from meridian.ingestion.gmail.store import GmailStore

_STRUCTURED_SOURCES = {"gmail", "calendar"}
_ALL_SOURCES = ("gmail", "calendar", "docs", "local_files")


@dataclass
class EntityGraphStats:
    items_processed: int = 0
    items_skipped_unchanged: int = 0
    items_deleted: int = 0
    mentions_recorded: int = 0
    chunks_failed: int = 0
    duration_ms: float = 0.0

    def merge(self, other: "EntityGraphStats") -> None:
        self.items_processed += other.items_processed
        self.items_skipped_unchanged += other.items_skipped_unchanged
        self.items_deleted += other.items_deleted
        self.mentions_recorded += other.mentions_recorded
        self.chunks_failed += other.chunks_failed
        self.duration_ms += other.duration_ms


def _gmail_identities(row: Any) -> list[tuple[PersonIdentity, str]]:
    identities = []
    if row["sender"]:
        identities.append((parse_person_header(row["sender"]), row["sender"]))
    for raw in json.loads(row["recipients"]):
        if raw:
            identities.append((parse_person_header(raw), raw))
    return identities


def _calendar_person_identity(email: str | None, display_name: str | None) -> PersonIdentity | None:
    email_norm = (email or "").strip().lower() or None
    name = (display_name or "").strip() or email_norm
    if not name:
        return None
    return PersonIdentity(display_name=name, email=email_norm)


def _calendar_identities(row: Any) -> list[tuple[PersonIdentity, str]]:
    identities = []
    organizer = _calendar_person_identity(row["organizer_email"], None)
    if organizer is not None:
        identities.append((organizer, row["organizer_email"]))
    for attendee in json.loads(row["attendees"]):
        identity = _calendar_person_identity(attendee.get("email"), attendee.get("display_name"))
        if identity is not None:
            surface = attendee.get("email") or attendee.get("display_name") or ""
            identities.append((identity, surface))
    return identities


def _gmail_item(row: Any) -> tuple[str, str, list[tuple[PersonIdentity, str]]]:
    return row["message_id"], row["content_hash"] or "", _gmail_identities(row)


def _calendar_item(row: Any) -> tuple[str, str, list[tuple[PersonIdentity, str]]]:
    item_id = f"{row['calendar_id']}:{row['event_id']}"
    return item_id, row["source_updated_at"] or "", _calendar_identities(row)


def run_structured_pass(
    source: str,
    db_path: Path,
    entity_store: EntityGraphStore,
    *,
    force: bool = False,
    logger: logging.Logger | None = None,
) -> EntityGraphStats:
    """extracts PERSON identities from a source's own raw ingestion
    store - Gmail sender/recipients headers, Calendar organizer/attendee
    emails - the structured signal source_readers.py deliberately omits
    from the index. Docs and local_files have no such signal and are
    skipped entirely."""
    stats = EntityGraphStats()
    start = time.monotonic()

    if source not in _STRUCTURED_SOURCES or not db_path.exists():
        return stats

    if source == "gmail":
        rows = GmailStore(db_path).get_all_messages()
        item_specs = [_gmail_item(row) for row in rows]
    else:
        rows = CalendarStore(db_path).get_all_events()
        item_specs = [_calendar_item(row) for row in rows]

    current_ids = {item_id for item_id, _, _ in item_specs}
    for stale_id in entity_store.get_processed_item_ids(source, "structured") - current_ids:
        entity_store.delete_mentions_for_item(source, stale_id, "structured")
        entity_store.clear_processed(source, stale_id, "structured")
        stats.items_deleted += 1

    for item_id, change_signal, identities in item_specs:
        if not force and entity_store.get_change_signal(source, item_id, "structured") == change_signal:
            stats.items_skipped_unchanged += 1
            continue

        entity_store.delete_mentions_for_item(source, item_id, "structured")
        for identity, surface_text in identities:
            entity_id = person_entity_id(identity)
            entity_store.upsert_entity(
                entity_id, "PERSON", person_identity_key(identity), identity.display_name, identity.email
            )
            entity_store.add_mention(entity_id, source, item_id, None, surface_text, "structured")
            stats.mentions_recorded += 1
        entity_store.set_processed(source, item_id, "structured", change_signal)
        stats.items_processed += 1

    stats.duration_ms = (time.monotonic() - start) * 1000
    if logger is not None:
        logger.info(
            "entity_graph structured pass complete",
            extra={
                "operation": "entity_graph.structured",
                "status": "success",
                "duration_ms": stats.duration_ms,
                "source": source,
            },
        )
    return stats


def run_ner_pass(
    source: str,
    index_store: IndexStore,
    entity_store: EntityGraphStore,
    nlp: Any,
    name_index: dict[str, str],
    *,
    entity_types: set[str] = DEFAULT_ENTITY_TYPES,
    force: bool = False,
    logger: logging.Logger | None = None,
) -> EntityGraphStats:
    """runs NER over every unique parent-text window already indexed for
    this source. name_index maps a normalized display name to the
    entity_id of an already-known, email-backed PERSON - a PERSON span
    matching one of those links to that entity instead of creating a new
    name-only one. a chunk that makes NER raise is logged and skipped,
    never crashing the whole run."""
    stats = EntityGraphStats()
    start = time.monotonic()

    rows = index_store.get_chunks_with_embeddings(source)
    items: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        items[row["source_item_id"]].append(row)

    for stale_id in entity_store.get_processed_item_ids(source, "ner") - set(items):
        entity_store.delete_mentions_for_item(source, stale_id, "ner")
        entity_store.clear_processed(source, stale_id, "ner")
        stats.items_deleted += 1

    for item_id, item_rows in items.items():
        current_signal = index_store.get_change_signal(source, item_id) or ""
        if not force and entity_store.get_change_signal(source, item_id, "ner") == current_signal:
            stats.items_skipped_unchanged += 1
            continue

        entity_store.delete_mentions_for_item(source, item_id, "ner")
        seen_parents: set[tuple[str, str, str]] = set()
        for row in item_rows:
            key = (row["source"], row["source_item_id"], row["parent_text"])
            if key in seen_parents:
                continue
            seen_parents.add(key)

            try:
                extracted = extract_entities(nlp, row["parent_text"], entity_types=entity_types)
            except Exception:
                if logger is not None:
                    logger.warning(
                        "entity_graph NER failed on chunk, skipping",
                        extra={
                            "operation": "entity_graph.extract",
                            "status": "error",
                            "duration_ms": 0,
                            "source": source,
                            "source_item_id": item_id,
                            "chunk_id": row["chunk_id"],
                        },
                        exc_info=True,
                    )
                stats.chunks_failed += 1
                continue

            for ent in extracted:
                if ent.label == "PERSON":
                    linked_entity_id = name_index.get(normalize_text(ent.text))
                    if linked_entity_id is not None:
                        entity_id = linked_entity_id
                    else:
                        entity_id = text_entity_id("PERSON", ent.text)
                        entity_store.upsert_entity(entity_id, "PERSON", text_identity_key(ent.text), ent.text)
                else:
                    entity_id = text_entity_id(ent.label, ent.text)
                    entity_store.upsert_entity(entity_id, ent.label, text_identity_key(ent.text), ent.text)

                entity_store.add_mention(entity_id, source, item_id, row["chunk_id"], ent.text, "ner")
                stats.mentions_recorded += 1

        entity_store.set_processed(source, item_id, "ner", current_signal)
        stats.items_processed += 1

    stats.duration_ms = (time.monotonic() - start) * 1000
    if logger is not None:
        logger.info(
            "entity_graph NER pass complete",
            extra={
                "operation": "entity_graph.ner",
                "status": "success",
                "duration_ms": stats.duration_ms,
                "source": source,
            },
        )
    return stats


def run_topic_pass(
    source: str,
    index_store: IndexStore,
    entity_store: EntityGraphStore,
    *,
    client: Any,
    model: str,
    analyzer: Any,
    force: bool = False,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> EntityGraphStats:
    """links each item to a topic node (entity_graph/topic_graph.py) so
    EntityGraphStore.items_sharing_topic_with() can later answer "what else
    is about this" via a graph traversal, not a fresh entity-overlap query
    - this is what makes cross-thread context merging real for items that
    share a subject but no common person/org entity. Uses only the first
    indexed chunk per item as that item's representative text/embedding -
    good enough for topic assignment, unlike NER which needs every chunk -
    keeping this to at most one Claude call per not-yet-linked item. Costs
    a real LLM call per new item, so unlike run_ner_pass this is opt-in
    (see --link-topics in entity_graph/__main__.py), not part of the free
    default run."""
    stats = EntityGraphStats()
    start = time.monotonic()

    rows = index_store.get_chunks_with_embeddings(source)
    items: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        items[row["source_item_id"]].append(row)

    for stale_id in entity_store.get_processed_item_ids(source, "topic") - set(items):
        entity_store.clear_processed(source, stale_id, "topic")
        stats.items_deleted += 1

    for item_id, item_rows in items.items():
        current_signal = index_store.get_change_signal(source, item_id) or ""
        if not force and entity_store.get_change_signal(source, item_id, "topic") == current_signal:
            stats.items_skipped_unchanged += 1
            continue

        representative = item_rows[0]
        embedding = np.frombuffer(representative["embedding"], dtype=np.float32)
        try:
            link_item_to_topic(
                source, item_id, representative["parent_text"], embedding, entity_store,
                client=client, model=model, analyzer=analyzer, logger=logger, audit_log_dir=audit_log_dir,
            )
        except Exception:
            if logger is not None:
                logger.warning(
                    "entity_graph topic pass failed on item, skipping",
                    extra={
                        "operation": "entity_graph.topic",
                        "status": "error",
                        "duration_ms": 0,
                        "source": source,
                        "source_item_id": item_id,
                    },
                    exc_info=True,
                )
            stats.chunks_failed += 1
            continue

        entity_store.set_processed(source, item_id, "topic", current_signal)
        stats.items_processed += 1

    stats.duration_ms = (time.monotonic() - start) * 1000
    if logger is not None:
        logger.info(
            "entity_graph topic pass complete",
            extra={
                "operation": "entity_graph.topic",
                "status": "success",
                "duration_ms": stats.duration_ms,
                "source": source,
            },
        )
    return stats


def _build_name_index(entity_store: EntityGraphStore) -> dict[str, str]:
    return {
        normalize_text(row["display_name"]): row["entity_id"]
        for row in entity_store.list_person_entities_with_email()
    }


def run_extraction(
    ingestion_dir: Path,
    index_store: IndexStore,
    entity_store: EntityGraphStore,
    nlp: Any,
    *,
    sources: list[str] | None = None,
    force: bool = False,
    entity_types: set[str] = DEFAULT_ENTITY_TYPES,
    logger: logging.Logger | None = None,
) -> dict[str, EntityGraphStats]:
    """the structured pass runs first for every requested source that has
    one, so email-backed people exist before the NER pass attempts any
    free-text linking."""
    sources = sources or list(_ALL_SOURCES)
    results = {source: EntityGraphStats() for source in sources}

    for source in sources:
        if source in _STRUCTURED_SOURCES:
            db_path = ingestion_dir / source / f"{source}.db"
            results[source].merge(
                run_structured_pass(source, db_path, entity_store, force=force, logger=logger)
            )

    name_index = _build_name_index(entity_store)

    for source in sources:
        results[source].merge(
            run_ner_pass(
                source,
                index_store,
                entity_store,
                nlp,
                name_index,
                entity_types=entity_types,
                force=force,
                logger=logger,
            )
        )

    return results
