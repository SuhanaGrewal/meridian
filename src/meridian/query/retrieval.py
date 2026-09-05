from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from meridian.indexing.hybrid_search import hybrid_search
from meridian.indexing.store import IndexStore
from meridian.query.date_range import chunk_in_range
from meridian.query.reranker import rerank

AbstainReason = Literal["no_candidates", "no_candidates_in_date_range", "low_confidence", "no_upcoming_match"]
# "no_upcoming_match" is never returned by retrieve() itself - it's set by
# answer.py::ask() when a forward-looking date query (e.g. "upcoming
# flights") finds nothing even after falling back to an unfiltered search,
# so the abstain message can say plainly "nothing upcoming, and no past
# record either" instead of the more generic date-range message.


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source: str
    source_item_id: str
    parent_text: str
    metadata: dict
    confidence: float


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    confidence: float
    abstained: bool
    abstain_reason: AbstainReason | None


def _fetch_and_filter_candidates(
    store: IndexStore,
    chunk_ids: list[str],
    date_range: tuple | None,
) -> list[sqlite3.Row]:
    """resolves fused search ids into full rows, applies the date filter (if
    any), and collapses multiple child-chunk hits from the same parent into
    one candidate - there's no separate parent table, so (source,
    source_item_id, parent_text) is the correct dedup key. preserves the
    input's rank order throughout."""
    rows = []
    for chunk_id in chunk_ids:
        row = store.get_chunk_row(chunk_id)
        if row is not None:
            rows.append(row)

    if date_range is not None:
        rows = [
            row
            for row in rows
            if chunk_in_range(row["source"], json.loads(row["metadata_json"]), date_range)
        ]

    seen_parents: set[tuple[str, str, str]] = set()
    deduped = []
    for row in rows:
        key = (row["source"], row["source_item_id"], row["parent_text"])
        if key in seen_parents:
            continue
        seen_parents.add(key)
        deduped.append(row)

    return deduped


def retrieve(
    store: IndexStore,
    question: str,
    question_embedding: np.ndarray,
    *,
    reranker: Any,
    date_range: tuple | None = None,
    source: str | None = None,
    logger: logging.Logger | None = None,
    initial_pool_k: int = 25,
    rerank_pool: int = 10,
    top_k: int = 5,
    abstain_threshold: float = 0.5,
) -> RetrievalResult:
    """the full retrieval pipeline: hybrid search for an initial candidate
    pool, resolve/date-filter/dedup to parent-level candidates, rerank on
    parent_text (the same text that grounds the final answer), keep the
    top_k, and abstain if the single best match isn't confident enough."""
    fused = hybrid_search(store, question, question_embedding, k=initial_pool_k, source=source)
    if not fused:
        return RetrievalResult(chunks=[], confidence=0.0, abstained=True, abstain_reason="no_candidates")

    chunk_ids = [chunk_id for chunk_id, _ in fused]
    candidates = _fetch_and_filter_candidates(store, chunk_ids, date_range)

    if not candidates:
        reason = "no_candidates_in_date_range" if date_range is not None else "no_candidates"
        return RetrievalResult(chunks=[], confidence=0.0, abstained=True, abstain_reason=reason)

    pool = candidates[:rerank_pool]
    scores = rerank(reranker, question, [row["parent_text"] for row in pool])

    ranked = sorted(zip(pool, scores), key=lambda item: item[1], reverse=True)[:top_k]

    chunks = [
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            source=row["source"],
            source_item_id=row["source_item_id"],
            parent_text=row["parent_text"],
            metadata=json.loads(row["metadata_json"]),
            confidence=score,
        )
        for row, score in ranked
    ]

    top_confidence = chunks[0].confidence if chunks else 0.0
    abstained = top_confidence < abstain_threshold

    if logger is not None:
        logger.info(
            "query retrieval complete",
            extra={
                "operation": "query.retrieve",
                "status": "success",
                "duration_ms": 0,
                "candidates_found": len(candidates),
                "top_confidence": top_confidence,
                "abstained": abstained,
            },
        )

    return RetrievalResult(
        chunks=chunks,
        confidence=top_confidence,
        abstained=abstained,
        abstain_reason="low_confidence" if abstained else None,
    )
