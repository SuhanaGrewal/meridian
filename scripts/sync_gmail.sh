#!/bin/bash
# Wrapper invoked by the com.meridian.gmailsync launchd job every 10
# minutes. Runs incremental Gmail sync, then reindexes just the gmail
# source so newly-synced mail is actually queryable, not just downloaded.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

"$PROJECT_DIR/.venv/bin/python" -m meridian.ingestion.gmail
"$PROJECT_DIR/.venv/bin/python" -m meridian.indexing --source gmail
