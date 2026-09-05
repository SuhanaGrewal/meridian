#!/bin/bash
# Wrapper invoked by the com.meridian.autosync launchd job every 10
# minutes. Runs incremental sync for every source (Gmail, Calendar, Docs,
# local files), then reindexes everything - incremental, so this is cheap
# when little has actually changed.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
PYTHON="$PROJECT_DIR/.venv/bin/python"

"$PYTHON" -m meridian.ingestion.gmail
"$PYTHON" -m meridian.ingestion.calendar
"$PYTHON" -m meridian.ingestion.docs

# local_files exits 1 (by design, not a crash) when MERIDIAN_NOTES_FOLDER
# isn't configured - under `set -e` that would otherwise kill this whole
# script and skip indexing entirely. Only run it when the folder is
# actually configured, same check the command itself makes.
if grep -qE '^MERIDIAN_NOTES_FOLDER=.+' "$PROJECT_DIR/.env" 2>/dev/null; then
    "$PYTHON" -m meridian.ingestion.local_files
fi

"$PYTHON" -m meridian.indexing
