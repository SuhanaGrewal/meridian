from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from meridian.entity_graph.store import EntityGraphStore
from meridian.indexing.vector_search import cosine_similarity_top_k
from meridian.query.anthropic_client import call_claude
from meridian.redaction.tokenize import tokenize_for_external_call, untokenize
from meridian.security.audit_log import record_event

# above this cosine similarity, a chunk is considered "about" an existing
# topic rather than needing a new one minted for it. Chosen conservatively
# high - a missed merge (two topic nodes for the same real subject) is a
# minor loss of recall in items_sharing_topic_with(); a false merge (two
# unrelated items wrongly linked) actively pollutes traversal results, so
# this errs toward the former.
_SIMILARITY_THRESHOLD = 0.6

LABEL_TOPIC_SYSTEM_PROMPT = (
    "Read the text below and respond with a short topic label (2-5 words) "
    "capturing what it is substantively about - a concrete subject, "
    "project, or recurring matter, not a generic category like 'email' or "
    "'meeting'. Respond with ONLY the label, nothing else - no "
    "punctuation, no explanation."
)


def _label_topic(
    text: str, *, client: Any, model: str, analyzer: Any,
    logger: logging.Logger | None = None, audit_log_dir: Path | None = None,
) -> str:
    tokenization = tokenize_for_external_call(text, analyzer=analyzer, logger=logger)
    if audit_log_dir is not None:
        record_event(
            audit_log_dir, "llm.external_call",
            {"operation": "entity_graph.topic_label", "entity_counts": tokenization.entity_counts},
        )
    raw = call_claude(
        client, model=model, system=LABEL_TOPIC_SYSTEM_PROMPT, user_message=tokenization.tokenized_text,
        max_tokens=20, logger=logger,
    )
    label = untokenize(raw, tokenization.mapping).strip()
    return label or "Untitled topic"


def link_item_to_topic(
    source: str,
    source_item_id: str,
    text: str,
    embedding: np.ndarray,
    entity_store: EntityGraphStore,
    *,
    client: Any,
    model: str,
    analyzer: Any,
    similarity_threshold: float = _SIMILARITY_THRESHOLD,
    logger: logging.Logger | None = None,
    audit_log_dir: Path | None = None,
) -> str:
    """links one item to a topic node - reusing an existing topic if the
    item's embedding is a close enough match (brute-force cosine search,
    same approach indexing/vector_search.py already uses for retrieval),
    otherwise minting a new topic node labeled by one Claude call. Recording
    the edge here is what makes EntityGraphStore.items_sharing_topic_with()
    a real graph traversal (item -> topic -> other items) rather than a
    fresh similarity computation on every query."""
    topics = entity_store.list_topics_with_embeddings()
    node = f"item:{source}:{source_item_id}"

    if topics:
        topic_embeddings = np.stack(
            [np.frombuffer(row["embedding"], dtype=np.float32) for row in topics]
        )
        top = cosine_similarity_top_k(np.asarray(embedding, dtype=np.float32), topic_embeddings, k=1)
        if top and top[0][1] >= similarity_threshold:
            matched = topics[top[0][0]]
            entity_store.add_graph_edge(node, f"topic:{matched['topic_id']}", "about_topic")
            return matched["topic_id"]

    label = _label_topic(text, client=client, model=model, analyzer=analyzer, logger=logger, audit_log_dir=audit_log_dir)
    topic_id = str(uuid.uuid4())
    entity_store.add_topic(topic_id, label, embedding)
    entity_store.add_graph_edge(node, f"topic:{topic_id}", "about_topic")
    return topic_id
