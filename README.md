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
    local_files/    Phase 5 — notes/transcripts folder watcher, content-hash dedup
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

Skeleton only — no pipeline logic implemented yet. Phases are built and
confirmed one at a time; see `CLAUDE.md` in this repo for the working
agreement.

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
