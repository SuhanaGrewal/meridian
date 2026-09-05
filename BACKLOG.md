# Backlog

Running list of known gaps and improvements found while testing Meridian
against real data, beyond the 12 core phases in `CLAUDE.md`. Add to this as
we find more. Nothing here is scheduled until explicitly picked up.

## Next up

### 1. "Upcoming/future" date filtering
`query/date_range.py` only recognizes phrases that look at the present or
past ("today," "this week," "last month," "last N days," a weekday name,
etc.) — there is no phrase for "upcoming," "next week," "future," anything
forward-looking, in either direction. Found via: asking "what flights do I
have booked" returned an already-happened May 2026 flight with no way to
ask for future-only results instead.

What it'd take:
- Add forward-looking phrases to `extract_date_range()` (e.g. "upcoming,"
  "next week," "next month," "in the next N days") returning a
  present-to-future window instead of a past/current one.
- Decide how this interacts with Gmail: an email's `sent_at` is always in
  the past even when it describes a future event (e.g. a flight
  confirmation) — a true "upcoming flights" filter would need to read
  travel *dates mentioned in the content*, not the email's send date. That's
  a materially harder feature (structured date extraction from free text) —
  worth explicitly scoping as in/out before starting.
- Calendar is the straightforward case: `start_at` is a real forward-dated
  field, so "upcoming calendar events" is a clean, achievable filter today.

## Fixed

### 7. Digest crashes on first run after any full backfill (prompt too long) — FIXED
`digest/gather.py` asks each source's store for "what's new since `since`."
`gmail/store.py::list_messages_since` and `local_files/store.py`'s
equivalent both filter on `updated_at` (when the row was last written to
the *local* database) instead of the content's real-world date
(`sent_at` for Gmail, `mtime_ns` for local files). Right after any full
backfill, every row's `updated_at` is "just now," so the very first digest
run sweeps in the *entire* mailbox — not just genuinely recent messages —
and blows past Claude's context limit (`prompt is too long: 206771 tokens
> 200000 maximum`, hit on a real 1,198-message mailbox). `docs/store.py`
does NOT have this bug — it already correctly filters on `modified_time`,
the doc's real Google-side edit date.
- Fix: change `list_messages_since` (gmail) and its local_files equivalent
  to filter on the real content timestamp (`sent_at`, `mtime_ns`) instead
  of `updated_at`, matching what `docs/store.py` already does correctly.
- No workaround via CLI flags — `--lookback-hours` doesn't help, since the
  bug is in the WHERE clause itself, not the window calculation.

### 2. Network timeouts crash the whole sync instead of retrying — FIXED
`common/google_api.py`'s `execute_with_retry` only retries `RateLimitedError`
and `TransientHttpError` — a raw connection-level timeout (no HTTP response
at all) isn't either of those, so it isn't retried and crashes the entire
ingestion run. Found via: a real Gmail full-backfill died on a single
message's `TimeoutError` mid-sync. Data already fetched wasn't lost
(committed per-message), but the whole run had to restart from scratch
since `_full_backfill` only saves its resume point at the very end, not
incrementally.
- Fix: broaden the retryable exception set in `retry_with_backoff` to
  include connection-level errors (`TimeoutError`, `ConnectionError`, etc.),
  not just Google API error responses.
- Related, smaller: consider checkpointing `_full_backfill`'s progress
  page-by-page instead of only at the end, so a crash partway through a
  large mailbox doesn't force a full restart.

## Also found, not yet actioned

### 3. No scheduler — nothing runs automatically
Every command (ingestion, indexing, digest) is one-shot, run-by-hand only.
"Sync every 5 minutes" and "nightly digest" both require an external
`launchd` (macOS) job wrapping these commands — doesn't exist yet.

### 4. `query` can't handle broad/open-ended asks
Questions like "summarize my recent emails" or "what is my CV like"
structurally can't be answered well by the fact-lookup retrieval path (it
scores individual small chunks against the question — no single chunk is
"about" a broad meta-question, so it correctly abstains rather than
hallucinate). The `digest` command is the right tool for "gather recent
stuff," but there's no routing between the two — a user has to already know
which tool fits which question shape.
- Possible fix: a lightweight router in front of `query` that detects a
  broad/summarization-shaped question and redirects to gather-style
  retrieval (everything in a window) instead of top-k relevance search.

### 5. No consumer-facing interface
CLI-only today — no chat window, no notifications when a digest is ready.
Scoped earlier at roughly 1-2 weeks for a basic local web chat UI +
native macOS notification, separate from the "installable by a
non-technical person" problem (bigger, includes OAuth consent-screen
verification concerns).

### 6. Cosmetic: HuggingFace Hub warning on every query
`sentence-transformers` prints "You are sending unauthenticated requests to
the HF Hub..." on every run. Harmless (models are already cached locally),
but noisy. Fix: `export HF_HUB_OFFLINE=1`, or bake a quiet default into the
code once models are confirmed cached.
