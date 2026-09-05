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
  entity_graph/     Phase 9 — entity extraction & cross-source linking
  digest/           Phase 10 — LangGraph digest pipeline with human-in-the-loop approval
  security/         Phase 11 — audit logging, scoped keys, encrypted storage, validation
  common/           shared utilities (logging, config, metrics) used across phases

config/             configuration files
data/               local index & ingested data (gitignored)
logs/               structured logs (gitignored)
tests/              eval harness & unit tests (Phase 12)
```

## Status

Phase 1 (Google OAuth), Phase 2 (Gmail ingestion), Phase 3 (Calendar
ingestion), Phase 4 (Docs ingestion), Phase 5 (local files ingestion),
Phase 6 (redaction/tokenization engine), Phase 7 (indexing), Phase 8
(query), Phase 9 (entity graph), Phase 10 (digest), Phase 11 (security),
and Phase 12 (eval harness) are implemented. Phases are built and
confirmed one at a time; see `CLAUDE.md` in this repo for the working
agreement.

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

Phase 8 (query) is the first live call site — it tokenizes the whole
prompt once before sending it to Claude and untokenizes the response
once. You can still try the round trip manually on any text:

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

### Phase 8 (Query)

No Google auth needed — operates entirely on the local index built by
Phase 7. Run:

```
python -m meridian.query "what's on my calendar this week"
```

**This works fully without an `LLM_API_KEY`** — it retrieves the most
relevant chunks (hybrid vector + keyword search, reranked by a local
cross-encoder), applies any date-range phrase found in the question
("this week", "last month", "last Tuesday", etc. — parsed with the
standard library only, no network call), and prints the retrieved context
plus a confidence score instead of a generated answer. If nothing relevant
enough is found, it says so directly instead of guessing (an "abstain",
with a specific reason: no matches at all, matches but none in the
requested date range, or matches that aren't confident enough).

To get a real generated answer instead of just retrieved context, set
`LLM_API_KEY` in `.env` (an [Anthropic API key](https://console.anthropic.com/settings/keys))
and optionally `LLM_MODEL` (defaults to `claude-haiku-4-5`, the cheapest
current model — a typical question costs well under a cent). Every claim
in a generated answer cites the bracketed source number(s) it came from,
and the exact context sent to Claude has names/emails/phone
numbers/addresses replaced with placeholders (`<PERSON_1>`, etc.) by
Phase 6's redaction step first, substituted back only after the response
comes back — so raw personal data is never what actually leaves the
machine.

Other flags: `--source gmail` to search one source only, `--top-k 3` to
change how many chunks are retrieved, `--model claude-sonnet-5` to
override the model for one run.

**Follow-up tracking**: when an `LLM_API_KEY` is set, every question asked
here is recorded to `data/query/query_history.db`
(`query/history_store.py`) and classified (one small Claude call) as
either a plain fact lookup or a "waiting on something" question (e.g.
"did I get a reply about X"). Only the latter kind matters going
forward — the next `digest run` re-checks every still-open one against
the current index and, if it's still not resolved, opens the digest by
calling it out explicitly rather than letting it quietly age out. See
Phase 10 below.

Known limitation: date-range phrases are computed in UTC calendar days,
not your local wall-clock day — fine for a personal tool, but "today"
could be off by a few hours right around midnight depending on your
timezone.

A test that makes a real (paid) Claude API call exists
(`tests/query/test_answer_real.py`) but only runs if you explicitly set
`MERIDIAN_RUN_LIVE_LLM_TESTS=1` in addition to `LLM_API_KEY` — it's
skipped by default so the regular test suite never spends real money.

### Phase 9 (Entity graph)

No Google auth needed for this run itself — operates on data already
ingested/indexed by earlier phases. Run after Phase 7 (indexing) has run
at least once:

```
python -m meridian.entity_graph
```

Answers "who/what is mentioned, and where else does it show up" by
combining two passes per source:

- A **structured pass** (Gmail and Calendar only) reads each source's own
  raw ingestion data directly — Gmail's sender/recipient headers, and
  Calendar's organizer/attendee email addresses — since these carry real
  identity information (email addresses) that never made it into the
  search index.
- An **NER pass** (all four sources) runs local entity recognition
  (spaCy's `en_core_web_lg` — the same model already required for Phase
  6, used directly rather than through Presidio, since Presidio has no
  organization/place recognizer) over every indexed chunk, extracting
  people, organizations, places, and events mentioned in the text.

A person mentioned by name in free text (a Doc, a Gmail body, a note) is
linked back to an already-known email-backed person when the names match
exactly — this is how the same "Jane Doe" showing up as a Gmail sender,
a Calendar attendee, and a name mentioned in a Google Doc all resolve to
one entity instead of three. Both passes are incremental (re-running only
processes what changed) and dead-letter safe (a chunk that breaks NER is
logged and skipped, never crashing the run).

Pass `--source gmail` (repeatable) to limit extraction to specific
sources, or `--full-reextract` to reprocess everything regardless of what
changed. Stores everything in `data/entity_graph/entity_graph.db`.

Inspect what got stored:

```
sqlite3 data/entity_graph/entity_graph.db "select entity_type, count(*) from entities group by entity_type;"
sqlite3 data/entity_graph/entity_graph.db "select entity_id, display_name from entities e where (select count(distinct source) from entity_mentions m where m.entity_id = e.entity_id) > 1;"
```

#### Topic graph (cross-thread context, opt-in)

`entities`/`entity_mentions` above link items that mention the same
*person*. A separate, additive `topics`/`graph_edges` pair of tables
answers a different question: which items are about the same *subject*,
even across differently-worded threads with no person in common (three
emails about "the Q3 budget" with three different subject lines, say).
Each item is linked to a topic node — an existing one if its embedding is
a close enough match, otherwise a new one labeled by one Claude call — and
`EntityGraphStore.items_sharing_topic_with(source, item_id)` traverses the
recorded edges (item → topic → other items) to answer "what else is about
this."

This costs a real LLM call per not-yet-linked item, so it's opt-in:

```
python -m meridian.entity_graph --link-topics
```

Combine with `--source` to scope it (e.g. `--source docs --link-topics`).

Known limitations, both documented in code rather than solved: name
matching is exact (after lowercasing/whitespace collapse) with no fuzzy
matching, so "Jon Smith" won't link to "John Smith"; and two different
real people who happen to share an exact name will incorrectly merge
into one entity. Both are reasonable trade-offs for a personal-scale tool
without pulling in a fuzzy-matching dependency.

### Phase 10 (Digest)

Meant to be invoked periodically (e.g. via cron/launchd — there's no
in-process scheduler anywhere in this project, same as every other
phase's one-shot CLI). Two subcommands, meant to be run as two separate
invocations — generate now, review later:

```
python -m meridian.digest run
python -m meridian.digest review
python -m meridian.digest review --approve <run_id>   # or --reject
```

`run` gathers what's new since the last reviewed digest (recent Gmail
messages, modified Docs, updated notes, notable entity mentions) plus
what's upcoming in the next few days (Calendar) — no search, embeddings,
or reranking involved, just each source's own raw data — and produces a
digest that **always pauses for human review before being considered
final**, per this project's "nothing acts autonomously" principle. Since
every Google API scope here is read-only, there's nothing to "send" —
approval means accepting the digest itself, not authorizing an outbound
action.

If `LLM_API_KEY` is set, `run` also re-checks every still-open "waiting
on something" question from Phase 8's query history (see above) against
the current index — one real `query.answer.ask()` call per open
question, the same pipeline a direct question would use. A question that
now has a confident, resolving answer is marked resolved and dropped
silently; anything still open is folded into the digest as its own item
and the digest prompt is instructed to always call it out explicitly,
never bury it in a routine-noise count.

This is the first phase built on **LangGraph** (a genuinely lightweight
addition — ~4MB across ~13 small packages, no LLM provider wrapper
needed since it calls the plain `anthropic` client directly, same as
Phase 8). The digest is a small state machine: gather → (nothing to
report, or) generate a summary → **pause for approval** → approved or
rejected. The pause uses LangGraph's `interrupt()` mechanism, which
requires saving execution state to disk so it can resume in a completely
separate process later — that's what `data/digest/checkpoints.db` is
(LangGraph's own internal bookkeeping, serialized opaquely — this
project's code never reads it directly). The actual human-facing
record — the digest text, its sources, and its approve/reject status —
lives in a second, plain, fully-readable file this project owns and
controls: `data/digest/digest.db`.

**Runs fully without an `LLM_API_KEY`** — `run` still gathers everything
and produces a plain grouped listing (no narrative summary) at zero
cost, and that listing still goes through the same approval step. Set
`LLM_API_KEY` (and optionally `LLM_MODEL`/`--model`) to get an actual
generated summary instead, redacted the same way Phase 8's answers are
(tokenized once before the call, untokenized once on the response).

Only one digest can be pending at a time — running `run` again before
reviewing the current one just reports that it's still pending, rather
than generating (and potentially paying for) an overlapping second
digest. `--lookback-hours` (default 24) sets how far back the very first
run looks before any review cursor exists; `--lookahead-days` (default
3) sets how far ahead Calendar looks for upcoming events, independent of
that cursor.

Inspect what got stored:

```
sqlite3 data/digest/digest.db "select run_id, status, window_start, window_end from digest_runs;"
```

`digest_text` and `sources_text` are encrypted at rest as of Phase 11 - a
raw `select digest_text ...` will show ciphertext; use
`python -m meridian.digest review` to see the plaintext digest.

Gmail content in the digest is filtered to your Primary inbox - gmail's
own CATEGORY_PROMOTIONS/SOCIAL/UPDATES/FORUMS labels are excluded
entirely, matching Gmail's own Primary tab (not just ads: a LinkedIn
invitation or shipping notification tagged CATEGORY_SOCIAL/UPDATES is
excluded too, by design). What's left is sorted so gmail's own
IMPORTANT-labeled mail comes first.

### Phase 11 (Security)

A cross-cutting phase touching several earlier ones, addressing five
things: audit logging, scoped API keys, encrypted local storage, input
validation, and dependency scanning. Two of these don't map cleanly onto
a single-user local tool with no server or multi-tenant concerns, so
they're addressed honestly below rather than forced into an enterprise
shape.

**Audit logging** — a durable, append-only, hash-chained log distinct
from the regular operational log (`logs/meridian.log`). Every line in
`logs/audit.log` includes a hash of its own content plus the previous
line's hash, so any edit or deletion is detectable:

```
python -m meridian.security verify-audit
```

Recorded events: OAuth consent granted / token refreshed (not a silent
reuse of a still-valid cached credential — that crosses no new
authorization boundary), every real call to Claude (with redaction entity
counts, never content — proof of what left the machine), and a digest
being approved or rejected. This is "detectable if altered," not
cryptographic non-repudiation against a hostile actor with full disk
access — an unrealistic threat model for a single-user local app, where
that actor would be the app's only user.

**Encrypted local storage** — extended narrowly to `digest/store.py`'s
`digest_text`/`sources_text` columns using the same Fernet primitive
already proven in `auth/token_store.py`'s OAuth token encryption, rather
than retrofitted across every store. Every other phase's README teaches
"inspect what got stored" via a raw `sqlite3 ... select` against
plaintext columns — encrypting those by default across 5 already-shipped
phases would silently break that documented convention with no clean
migration story for already-ingested historical data. The digest store
is the newest, smallest-blast-radius target, and arguably the most apt
anyway: it's LLM-synthesized content quoting across multiple sensitive
sources at once. The same `security/field_encryption.py` utility is
readily reusable to extend this to other stores later if warranted.

Key management was also hardened: `auth/token_store.py`'s encryption key
(previously a randomly generated file with no passphrase option) can now
optionally be derived from `MERIDIAN_ENCRYPTION_PASSPHRASE` via PBKDF2 —
zero-config installs see no change, since the fallback is exactly the
prior random-key behavior.

**Input validation** — a symlink-containment guard in the local files
scanner (a symlink inside your notes folder pointing outside it is
skipped, not silently followed and ingested), and a 200,000-character cap
on free-text fields across all four ingestion parsers, applied before
any hashing so change-detection stays consistent with the capped
content.

**Dependency scanning** — `pip-audit` (PyPA-maintained, free) is a dev
dependency. Run it periodically, e.g. before a release:

```
pip-audit
```

No CI workflow was added for this — the project has no CI at all today,
and building one solely to wrap a single command would be disproportionate
infrastructure for a solo project. If CI is added later for other reasons,
`pypa/gh-action-pip-audit` is a five-line addition.

**Scoped API keys** — mostly a documentation/operator concern, not code,
for a tool with no server and no multi-tenant surface:
- Google OAuth already requests the minimum 4 scopes (`gmail.readonly`,
  `calendar.readonly`, `documents.readonly`, `drive.readonly`) — nothing
  broader is ever requested.
- Anthropic API keys have no in-API scoping mechanism to restrict a key
  to a subset of capabilities (confirmed against Anthropic's own docs) —
  the closest realistic lever is Console-level: create a dedicated
  Anthropic Workspace for Meridian and set a key expiration (e.g. 90
  days) rather than "Never," rotating manually. This is operator
  configuration, not something this codebase can enforce.
- The one genuine code deliverable here is the log-scrubbing guard
  described below.

**Defense-in-depth log scrubbing** — `common/logging.py` now redacts any
registered secret value from every log line before it's written, so a
future accidental `logger.info(f"...{api_key}...")` can't leak a real
key or client secret into `logs/meridian.log`.

One-time manual smoke test, after any of the above changes:

```
python -m meridian.auth --force-refresh   # or a fresh consent flow
python -m meridian.security verify-audit  # confirms a new hash-chained line landed
python -m meridian.digest run
python -m meridian.digest review --approve <run_id>
sqlite3 data/digest/digest.db "select digest_text from digest_runs;"  # ciphertext
python -m meridian.digest review                                     # plaintext
python -m meridian.security verify-audit  # confirms the digest.reviewed event is intact too
```

### Phase 12 (Tests / eval harness)

A regression harness for the retrieval pipeline built in Phase 8, living
under `tests/eval/` (not a new `src/meridian/` module — `tests/` isn't
packaged for install, so there's no `python -m meridian.tests` CLI to
extend; it runs the same way as every other test, via plain `pytest`).

`tests/eval/golden_dataset.py` defines a small synthetic corpus (18
documents spanning all four ingestion sources) and 18 questions against
it — most single-source, a couple cross-source, a few designed to have
no answer in the corpus at all. `tests/eval/scoring.py` holds the scoring
math: precision, recall, reciprocal rank (mean rank of the first correct
result), and a citation-index extractor.

Two eval tests consume that dataset:

- `tests/eval/test_retrieval_eval.py` — fast, free, deterministic (fake
  embeddings/reranker), runs in the default `pytest` invocation alongside
  every other test. Asserts the retrieval pipeline finds the right
  sources at a threshold, and that every "no answer in the corpus"
  question actually causes an abstain.
- `tests/eval/test_answer_eval_real.py` — opt-in, gated exactly like
  `tests/query/test_answer_real.py` (`LLM_API_KEY` +
  `MERIDIAN_RUN_LIVE_LLM_TESTS=1`, skipped otherwise). Runs a bounded
  subset of the golden questions through the real embedder, cross-encoder
  reranker, and Claude, and asserts every `[N]` citation in the generated
  answer actually refers to a retrieved source — the concrete check
  behind "grounded, not hallucinated."

Run the fast suite same as always:

```
pytest
```

Run the real one (costs a small amount of real API usage):

```
LLM_API_KEY=<key> MERIDIAN_RUN_LIVE_LLM_TESTS=1 pytest tests/eval/test_answer_eval_real.py -v
```

## Scheduling (auto-sync, nightly digest & calendar notifications)

Every command in this project is a one-shot CLI with no built-in scheduler
(see `CLAUDE.md`'s "production-rigor" principle — this is deliberate, not
an oversight). To actually get every source syncing automatically, a digest
generated nightly, and calendar notifications firing, `scripts/install_launchd.sh`
installs three macOS `launchd` agents:

```
./scripts/install_launchd.sh
```

- **Full sync every 10 minutes** — runs Gmail, Calendar, Docs, and
  local-files ingestion (local-files skips itself gracefully if
  `MERIDIAN_NOTES_FOLDER` isn't set, rather than erroring the whole job),
  then reindexes everything incrementally, so anything new is actually
  queryable within minutes, not just downloaded.
- **Nightly digest** — fires once daily at 8am by default
  (`DIGEST_HOUR=7 ./scripts/install_launchd.sh` to change it). To restrict
  which days it actually runs a digest, set `DIGEST_DAYS` in `.env` (e.g.
  `DIGEST_DAYS=mon,wed,fri`) — this is checked by `scripts/nightly_digest.sh`
  itself, so changing it takes effect on the next firing with no need to
  reinstall the job. Leave `DIGEST_DAYS` empty to run every day.
- **Calendar notifications every minute** — a native macOS notification
  for any calendar event starting within a lead time (default 15 minutes,
  `CALENDAR_NOTIFY_LEAD_MINUTES` in `.env`). This is a one-shot check
  re-run every minute (via `StartInterval`), not a long-running background
  process — this project has no in-process daemon infrastructure anywhere,
  and a genuine daemon would need its own crash-restart and log-rotation
  handling for what's ultimately a personal, single-user tool. A
  `data/notifications/notifications.db` store dedupes so the same event
  doesn't re-alert on every check between the lead time and its actual
  start.

Safe to re-run `install_launchd.sh` any time (e.g. after changing
`DIGEST_HOUR`) — it reloads cleanly instead of erroring on an
already-installed job, and cleans up the older Gmail-only job name if
you'd installed that before every source was covered. Logs land in
`logs/launchd-autosync.log`, `logs/launchd-digest.log`, and
`logs/launchd-calendarnotify.log`, separate from Meridian's own
structured log.

Remove all three jobs with:

```
./scripts/uninstall_launchd.sh
```

## Inbox Intelligence

A new, separate track from the digest: proactive analysis of your inbox
rather than a periodic summary. Operates entirely on already-ingested
Gmail data (`data/ingestion/gmail/gmail.db`) - no new API scopes, no
network calls beyond the account-email lookup gmail sync already does.

**Stale threads ("your move")** - detects threads where the last message
wasn't from you and it's been quiet for a while:

```
python -m meridian.inbox_intelligence stale-threads
python -m meridian.inbox_intelligence stale-threads --min-days 5
```

Needs your account's own email address to know whose "move" it is - this
is captured automatically the next time `python -m meridian.ingestion.gmail`
runs (whether a fresh backfill or an incremental sync), no separate setup
step. If you see "Account email not captured yet," just run the gmail sync
once first.

**Soft-commitment tracking** - detects a promise the sender of an email
makes about their own future action ("I'll send this by Friday") and
converts it into a trackable follow-up. Unlike stale-threads, this makes
real Claude calls (redacted first, audit-logged, same as `query`/`digest`)
so it's a separate opt-in step, bounded by `--limit`:

```
python -m meridian.inbox_intelligence scan-commitments --limit 25
python -m meridian.inbox_intelligence commitments
python -m meridian.inbox_intelligence resolve-commitment <commitment_id>
```

`scan-commitments` only looks at messages it hasn't scanned before
(tracked in `data/inbox_intelligence/commitments.db`), skips
promotional/social/updates/forums mail and auto-replies before ever
calling the LLM, and only extracts commitments the sender made about
themselves (covers both directions across your mailbox, since you show up
as sender on outgoing mail and recipient on incoming mail). The LLM
extracts the deadline phrase verbatim (e.g. "by Friday") only - the actual
date is resolved deterministically in code from the message's real send
date, not asked of the LLM, since real testing showed LLM date arithmetic
is unreliable (see the query-recency note above). Absolute date references
("around the 9th of September") aren't resolved to a due date yet - only
weekday names and relative-day phrases are; unresolvable phrases show no
due date rather than a guessed one. `resolve-commitment` is manual only -
there's no automatic fulfillment detection.

Drafting replies in your voice is tracked in `BACKLOG.md`, not yet built.
Merging context across threads about the same topic is built (see the
topic graph under Phase 9 above); reminder intake is documented below.

**Reminder intake** - "remind me to meet with Nick" is recognized as a
task to track, not a question to answer, and (if a calendar is available)
gets a proposed free slot from the next week's actual calendar - a
deterministic scan of existing events for an open gap in business hours,
never an LLM guess at times. Nothing is ever booked - there's no
calendar-write path anywhere in this project to book it with even if it
wanted to:

```
python -m meridian.reminders add "meet with Nick"
python -m meridian.reminders list
python -m meridian.reminders dismiss <reminder_id>
```

### Talking to it in plain language

The commands above still exist, but you don't need to know them - `python
-m meridian.query "<anything>"` routes your question to the right place
automatically:

```
python -m meridian.query "hey any thread needs my approval"
python -m meridian.query "what commitments are open"
python -m meridian.query "mark the laptop drop-off commitment as done"
python -m meridian.query "when did I fly to London"
python -m meridian.query "summarize my recent emails"
python -m meridian.query "remind me to meet with Nick"
```

One cheap Claude call classifies the message into one of six categories -
stale threads, open commitments, "mark this resolved," a broad recent-
activity summary, a reminder/task, or a genuine fact question - before
routing. Stale threads and broad summaries come back as a natural
summary in prose, not a raw email dump - either will only quote the
actual message text if you explicitly ask to see it. A "mark as resolved"
request is matched against your currently open threads, commitments, and
reminders; if it's ambiguous (e.g. the same email produced both a stale
thread and a tracked commitment), it asks you to be more specific rather
than guessing. Once dismissed, a thread stays hidden from future
`stale-threads` results (`InboxIntelligenceStore` persists this - stale
threads used to be recomputed fresh every time with no memory of what
you'd already handled).
