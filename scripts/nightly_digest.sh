#!/bin/bash
# Wrapper invoked once daily by the com.meridian.nightlydigest launchd job.
# The plist fires every day at a fixed hour; this script is what actually
# decides whether today is a day the user wants a digest on, via
# DIGEST_DAYS in .env (comma-separated 3-letter day names, e.g.
# "mon,wed,fri"). Unset or empty DIGEST_DAYS means "every day."
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

DIGEST_DAYS=""
if [ -f "$PROJECT_DIR/.env" ]; then
    DIGEST_DAYS="$(grep -E '^DIGEST_DAYS=' "$PROJECT_DIR/.env" | tail -1 | cut -d= -f2-)"
fi

today="$(date +%a | tr '[:upper:]' '[:lower:]')"
if [ -n "$DIGEST_DAYS" ]; then
    case ",${DIGEST_DAYS}," in
        *",${today},"*) ;;
        *)
            echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) not scheduled to run on $today (DIGEST_DAYS=$DIGEST_DAYS), skipping"
            exit 0
            ;;
    esac
fi

"$PROJECT_DIR/.venv/bin/python" -m meridian.digest run
