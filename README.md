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
  redaction/        Phase 6 — call-time PII tokenization for external API calls
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
ingestion), Phase 4 (Docs ingestion), Phase 5 (local files ingestion),
Phase 6 (redaction/tokenization engine), and Phase 7 (indexing) are
implemented. Phases are built and confirmed one at a time; see `CLAUDE.md`
in this repo for the working agreement.

## Setup

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_lg  # required for phase 6 (redaction) - ~560MB, one-time
cp .env.example .env  # fill in OAuth client id/secret, notes folder path, etc.
```

Phase 7 (indexing) needs `sentence-transformers`, which requires PyTorch.
On macOS/Windows the default `pip install` gets a CPU-only build
automatically. **On Linux**, the default PyPI wheel bundles full CUDA
toolkits (multiple GB) even if you don't have a GPU — for a genuinely
CPU-only install, run this *before* `pip install -e ".[dev]"`:

```
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Its embedding model (`all-MiniLM-L6-v2`, ~90MB) downloads automatically on
first use — no manual step like spaCy's.

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

### Phase 6 (Redaction)

No Google auth needed. This phase is a **call-time utility, not a batch
job or a pipeline stage that runs on its own** — since local embeddings and
retrieval (Phase 7+) never leave the machine, the only real point of
external exposure is the moment something is actually sent to Claude's API
(the future query/answer flow and digest/drafting flow). So redaction
lives as two functions — `tokenize_for_external_call()` and
`untokenize()` — meant to be called immediately before and after an
external API call: tokenize right before sending, untokenize on the
response, then let the mapping (a plain in-memory dict) go out of scope.
Nothing is ever written to disk. There's no persistent store for this
phase.

Detected entities split into two groups:
- **Reversible** (`PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `HOME_ADDRESS`)
  get a unique numbered placeholder (`<PERSON_1>`, ...) recorded in the
  mapping, so a drafted reply can still coherently reference a real name or
  address once substituted back.
- **Hard secrets** (credit cards, government ID numbers, IBAN/crypto,
  IP/MAC addresses, API keys/passwords) become a fixed `[REDACTED]` marker
  and are **never added to the mapping** — there is no way for those
  values to reappear, even in a response.
- `LOCATION`, `DATE_TIME`, `URL`, and nationality/religion/political terms
  are deliberately left untouched — they're usually needed context (a
  meeting's place or time), not sensitive identifiers.

Since Phases 7/8/10 don't exist yet, there's no live call site to wire
this into today. Try the round trip manually:

```
python -m meridian.redaction "Contact John Smith at john@example.com, my address is 123 Main St"
```

Every call logs entity type + count to the structured log (never the
matched text itself).

### Phase 7 (Indexing)

No Google auth needed — operates entirely on already-ingested local data.
Run after any of Phases 2-5 have ingested something:

```
python -m meridian.indexing
```

Reads each source's ingestion database directly (read-only), splits each
item's text into small "child" chunks (for accurate search matches) linked
to larger "parent" context (for grounding an answer once a chunk is
found), embeds the children locally via `sentence-transformers`, and
stores everything — including the embeddings themselves — in one file:
`data/indexing/index.db`. Skips any item that hasn't changed since it was
last indexed, and removes chunks for anything deleted/trashed upstream.
Pass `--source gmail` (repeatable) to limit indexing to specific sources,
or `--full-reindex` to reprocess everything regardless of what changed.

Search is genuinely hybrid: vector similarity (exact cosine similarity via
plain numpy — brute-force, not an approximate index, since a personal
corpus is nowhere near the scale where approximation would pay off) and
keyword search (SQLite's built-in FTS5 — no extra dependency), merged via
reciprocal rank fusion so a chunk ranking well on either signal can surface.

Inspect what got stored:

```
sqlite3 data/indexing/index.db "select count(*) from chunks;"
```
