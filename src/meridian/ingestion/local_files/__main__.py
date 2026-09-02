from __future__ import annotations

import argparse
import sys

from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger
from meridian.ingestion.local_files.scan import run_scan
from meridian.ingestion.local_files.store import NotesStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan the local notes/transcripts folder into Meridian's local store."
    )
    parser.add_argument(
        "--force-rehash",
        action="store_true",
        help="Re-read and re-hash every file's content, bypassing the size/mtime short-circuit.",
    )
    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.ingestion.local_files.cli", log_dir=config.log_dir)

    if config.notes_folder is None:
        print("MERIDIAN_NOTES_FOLDER is not set. Set it in .env and try again.")
        sys.exit(1)

    store = NotesStore(config.ingestion_dir / "local_files" / "local_files.db")

    stats = run_scan(config.notes_folder, store, force_rehash=args.force_rehash, logger=logger)

    print(
        f"Local files scan complete: {stats.files_scanned} scanned, "
        f"{stats.notes_added} added, {stats.notes_updated} updated, "
        f"{stats.notes_skipped_unchanged} unchanged, {stats.notes_deleted} deleted, "
        f"{stats.parse_failures} parse failures in {stats.duration_ms:.0f}ms."
    )


if __name__ == "__main__":
    main()
