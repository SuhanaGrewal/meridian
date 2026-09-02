# Meridian

Local-first personal knowledge assistant. Connects to Gmail, Google Calendar,
Google Docs (read-only OAuth), and a local notes/transcripts folder; indexes
everything with hybrid search; answers questions with citations; and runs a
scheduled digest job whose output always lands in an approval queue — nothing
sends or executes automatically.

## Core principles

- **Local-first**: raw personal data never leaves the machine. Only redacted,
  summarized text goes to external APIs.
- **Grounded, not hallucinated**: every claim cites its exact source.
- **Human-gated**: nothing acts autonomously; all actions require explicit
  approval.
- **Incremental**: never reprocess unchanged data (Gmail History API,
  Calendar sync tokens, Docs revision IDs, content hashes for local files).
- **Production-rigor**: retries with backoff, dead-letter handling, idempotent
  processing, self-imposed throttling, rate-limit handling, structured
  logging, observability.

## Project layout

```
src/meridian/
  auth/             Phase 1 — Google OAuth (single consent, readonly scopes), token storage
  ingestion/
    gmail/          Phase 2 — Gmail polling + History API incremental sync
    calendar/       Phase 3 — Calendar polling + sync tokens
    docs/           Phase 4 — Docs polling + revision tracking
    local_files/    Phase 5 — notes/transcripts folder scanner, content-hash dedup
  redaction/        Phase 6 — PII scrubbing before anything leaves the machine
  indexing/         Phase 7 — structure-aware chunking, embeddings, hybrid search
  query/            Phase 8 — retrieval, rerank, grounded generation with citations
  knowledge_graph/  Phase 9 — entity extraction & cross-source linking
  digest/           Phase 10 — LangGraph digest pipeline with human-in-the-loop approval
  security/         Phase 11 — audit logging, scoped keys, encrypted storage, validation
  common/           shared utilities (logging, config, metrics) used across phases

config/             configuration files
data/               local index & ingested data (gitignored)
logs/               structured logs (gitignored)
tests/              eval harness & unit tests (Phase 12+)
```

## Status

Phase 1 (Google OAuth), Phase 2 (Gmail ingestion), Phase 3 (Calendar
ingestion), Phase 4 (Docs ingestion), and Phase 5 (local files ingestion)
are implemented. Phases are built and confirmed one at a time; see
`CLAUDE.md` in this repo for the working agreement.

## Setup

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in OAuth client id/secret, notes folder path, etc.
```

### Phase 1 prerequisites (Google OAuth)

Before running `python -m meridian.auth`, set up a Google Cloud project:

1. Create or select a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the Gmail API, Google Calendar API, Google Docs API, and Google Drive API.
3. Configure the OAuth consent screen (External + Testing mode is fine for
   personal use) and add your own Google account as a test user.
4. Create an OAuth 2.0 Client ID of type **Desktop app**.
5. Copy the client ID/secret into `.env` as `GOOGLE_OAUTH_CLIENT_ID` and
   `GOOGLE_OAUTH_CLIENT_SECRET`.

Then run `python -m meridian.auth` — a browser window opens asking you to
approve read-only access to Gmail, Calendar, Docs, and Drive. Credentials
are stored encrypted under `data/auth/`. Running it again reuses the stored
credentials (refreshing automatically if expired) without re-prompting.

### Phase 2 (Gmail ingestion)

Once Phase 1 auth is set up, run:

```
python -m meridian.ingestion.gmail
```

First run does a full backfill of your mailbox (respecting a deliberately
conservative self-imposed rate limit — this can take a while for a large
mailbox) and stores everything in `data/ingestion/gmail/gmail.db`. Running
it again only fetches what changed since the last run (via Gmail's History
API), so it's fast. Pass `--full-resync` to force a fresh full backfill
(e.g. if you want to re-pull everything). Set `GMAIL_SYNC_QUERY` in `.env`
(e.g. `newer_than:365d`) to scope the initial backfill to a narrower window
instead of your entire mailbox.

Inspect what got stored:

```
sqlite3 data/ingestion/gmail/gmail.db "select count(*) from messages;"
```

### Phase 3 (Calendar ingestion)

Once Phase 1 auth is set up, run:

```
python -m meridian.ingestion.calendar
```

Syncs only your primary calendar. First run does a full backfill and stores
everything in `data/ingestion/calendar/calendar.db`. Running it again only
fetches what changed since the last run (via Calendar's sync tokens), so
it's fast. Pass `--full-resync` to force a fresh full backfill. Set
`CALENDAR_SYNC_TIME_MIN` in `.env` (e.g. `2024-01-01T00:00:00Z`) to scope
the initial backfill to a narrower window instead of your calendar's entire
history — note this only affects the first/forced full sync, since once a
sync token exists, Google's API doesn't allow re-bounding incremental syncs
by time.

Inspect what got stored:

```
sqlite3 data/ingestion/calendar/calendar.db "select count(*) from events;"
```

### Phase 4 (Docs ingestion)

Once Phase 1 auth is set up, run:

```
python -m meridian.ingestion.docs
```

First run does a full backfill of every Google Doc you can see (via Drive's
file listing, since the Docs API itself can't enumerate documents) and
stores everything in `data/ingestion/docs/docs.db`. Running it again only
fetches what changed since the last run (via Drive's Changes API), skipping
any doc whose `modifiedTime` hasn't changed without even fetching its
content. Pass `--full-resync` to force a fresh full backfill. Set
`DOCS_SYNC_DRIVE_QUERY` in `.env` (e.g. `"'<folder_id>' in parents"`) to
scope the initial backfill to a narrower set of docs — note this only
affects the first/forced full sync, since Drive's Changes API takes no
query parameter at all once incremental syncing starts. An invalid/expired
page token is detected via a best-effort inference (Google doesn't document
an exact error contract here, unlike Calendar's documented 410) and
automatically falls back to a full resync.

Inspect what got stored:

```
sqlite3 data/ingestion/docs/docs.db "select count(*) from documents;"
```

### Phase 5 (Local files ingestion)

No Google auth needed — just set `MERIDIAN_NOTES_FOLDER` in `.env`, then run:

```
python -m meridian.ingestion.local_files
```

Unlike Phases 2-4, this isn't a backfill/incremental-sync split — listing a
local folder is free, so every run scans the whole folder (recursing into
subfolders, `.txt`/`.md` files only, dotfiles/dot-directories skipped).
Before re-reading a file's content, it first checks the file's size and
modified-time against what's stored and skips entirely if neither changed
— so re-running on an untouched folder does no real work. A file removed
from the folder is tombstoned every run. Pass `--force-rehash` to bypass
that check and re-read every file's content regardless. Stores everything
in `data/ingestion/local_files/local_files.db`.

Inspect what got stored:

```
sqlite3 data/ingestion/local_files/local_files.db "select count(*) from notes;"
```
