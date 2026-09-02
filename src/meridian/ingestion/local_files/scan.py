from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from meridian.ingestion.local_files.note_parser import NoteParseError, parse_note_file
from meridian.ingestion.local_files.store import NotesStore

DEFAULT_EXTENSIONS = {".txt", ".md"}


@dataclass
class ScanStats:
    files_scanned: int = 0
    notes_added: int = 0
    notes_updated: int = 0
    notes_skipped_unchanged: int = 0
    notes_deleted: int = 0
    parse_failures: int = 0
    duration_ms: float = 0.0


def _iter_note_files(notes_folder: Path, extensions: set[str]) -> Iterator[Path]:
    for path in sorted(notes_folder.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in extensions:
            continue

        relative_parts = path.relative_to(notes_folder).parts
        if any(part.startswith(".") for part in relative_parts):
            continue

        yield path


def _scan_one_file(
    path: Path,
    *,
    notes_folder: Path,
    store: NotesStore,
    stats: ScanStats,
    logger: logging.Logger | None = None,
    force_rehash: bool = False,
) -> None:
    stats.files_scanned += 1
    rel_path = path.relative_to(notes_folder).as_posix()
    stat = path.stat()
    existing = store.get_note_metadata(rel_path)

    if not force_rehash and existing is not None and existing == (stat.st_size, stat.st_mtime_ns):
        stats.notes_skipped_unchanged += 1
        return

    try:
        parsed = parse_note_file(path, relative_to=notes_folder, logger=logger)
    except NoteParseError as exc:
        store.record_dead_letter(rel_path, str(exc))
        stats.parse_failures += 1
        if logger is not None:
            logger.warning(
                f"failed to parse local file {rel_path}",
                extra={"operation": "local_files.parse_note", "status": "error", "duration_ms": 0},
            )
        return

    store.upsert_note(parsed)
    if existing is None:
        stats.notes_added += 1
    else:
        stats.notes_updated += 1


def run_scan(
    notes_folder: Path | None,
    store: NotesStore,
    *,
    extensions: set[str] = DEFAULT_EXTENSIONS,
    force_rehash: bool = False,
    logger: logging.Logger | None = None,
) -> ScanStats:
    start = time.monotonic()
    stats = ScanStats()

    if notes_folder is None or not notes_folder.is_dir():
        if logger is not None:
            logger.warning(
                f"notes folder not configured or does not exist: {notes_folder}",
                extra={"operation": "local_files.scan", "status": "error", "duration_ms": 0},
            )
        return stats

    seen_paths: set[str] = set()
    for path in _iter_note_files(notes_folder, extensions):
        seen_paths.add(path.relative_to(notes_folder).as_posix())
        _scan_one_file(
            path,
            notes_folder=notes_folder,
            store=store,
            stats=stats,
            logger=logger,
            force_rehash=force_rehash,
        )

    stats.notes_deleted = store.tombstone_missing(seen_paths)
    stats.duration_ms = round((time.monotonic() - start) * 1000, 2)

    if logger is not None:
        logger.info(
            "local files scan complete",
            extra={
                "operation": "local_files.scan",
                "status": "success",
                "duration_ms": stats.duration_ms,
                "files_scanned": stats.files_scanned,
                "notes_added": stats.notes_added,
                "notes_updated": stats.notes_updated,
                "notes_skipped_unchanged": stats.notes_skipped_unchanged,
                "notes_deleted": stats.notes_deleted,
                "parse_failures": stats.parse_failures,
            },
        )

    return stats
