from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Literal

from meridian.indexing.store import IndexStore
from meridian.query.date_range import chunk_in_range

AbstainReason = Literal["no_candidates", "no_candidates_in_date_range", "low_confidence"]


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
