from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from meridian.indexing.embedder import embed_chunks
from meridian.indexing.parent_child import build_chunks
from meridian.indexing.source_readers import (
    read_calendar_items,
    read_docs_items,
    read_gmail_items,
    read_local_files_items,
)
from meridian.indexing.store import IndexStore

_READERS = {
    "gmail": read_gmail_items,
    "calendar": read_calendar_items,
    "docs": read_docs_items,
    "local_files": read_local_files_items,
}


@dataclass
class IndexStats:
    items_indexed: int = 0
    items_skipped_unchanged: int = 0
    items_deleted: int = 0
    chunks_written: int = 0
    duration_ms: float = 0.0


def index_source(
    source: str,
    db_path: Path,
    store: IndexStore,
    embedder: Any,
    *,
    force: bool = False,
    logger: logging.Logger | None = None,
) -> IndexStats:
    """incrementally indexes one source: skips items whose change_signal is
    unchanged, re-chunks/re-embeds new or changed items, and reconciles
    deletions (anything previously indexed for this source that the reader
    no longer returns, because it was deleted/trashed upstream). force=True
    bypasses the unchanged check, re-processing every item regardless."""
    stats = IndexStats()
    start = time.monotonic()

    items = _READERS[source](db_path)
    seen_ids = {item.item_id for item in items}

    for stale_id in store.get_indexed_item_ids(source) - seen_ids:
        store.delete_item(source, stale_id)
        stats.items_deleted += 1

    for item in items:
        if not force and store.get_change_signal(source, item.item_id) == item.change_signal:
            stats.items_skipped_unchanged += 1
            continue

        records = build_chunks(item.text, has_headings=item.has_headings)
        if records:
            embeddings = embed_chunks(embedder, [r.text for r in records])
            store.upsert_item_chunks(source, item.item_id, records, embeddings, item.metadata)
            stats.chunks_written += len(records)
        else:
            store.delete_item(source, item.item_id)

        store.set_indexed(source, item.item_id, item.change_signal)
        stats.items_indexed += 1

    stats.duration_ms = round((time.monotonic() - start) * 1000, 2)

    if logger is not None:
        logger.info(
            f"indexing complete for {source}",
            extra={
                "operation": "indexing.index_source",
                "status": "success",
                "duration_ms": stats.duration_ms,
                "source": source,
                "items_indexed": stats.items_indexed,
                "items_skipped_unchanged": stats.items_skipped_unchanged,
                "items_deleted": stats.items_deleted,
                "chunks_written": stats.chunks_written,
            },
        )

    return stats


def run_indexing(
    ingestion_dir: Path,
    store: IndexStore,
    embedder: Any,
    *,
    sources: list[str] | None = None,
    force: bool = False,
    logger: logging.Logger | None = None,
) -> dict[str, IndexStats]:
    """runs index_source() for each requested source (default: all four),
    resolving each source's ingestion database path the same way every
    ingestion phase's CLI already does."""
    sources = sources or list(_READERS.keys())
    db_paths = {name: ingestion_dir / name / f"{name}.db" for name in _READERS}

    return {
        source: index_source(source, db_paths[source], store, embedder, force=force, logger=logger)
        for source in sources
    }
