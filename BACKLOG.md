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

### 3. No scheduler — nothing runs automatically (Gmail + digest fixed, rest still manual)
Every command (ingestion, indexing, digest) was one-shot, run-by-hand
only. `scripts/install_launchd.sh` now installs two macOS `launchd`
agents: Gmail sync every 10 minutes (then reindexes just the gmail
source), and a nightly digest at a configurable hour. `DIGEST_DAYS` in
`.env` restricts which days the digest actually runs (comma-separated
3-letter day names, e.g. `mon,wed,fri`; empty = every day) - checked by
`scripts/nightly_digest.sh` itself, not baked into the plist, so it's a
config setting rather than the "when the user logs in" login-screen
concept originally requested (there's no login/account system in this
local single-user tool for that to mean anything). `./scripts/uninstall_launchd.sh`
removes both jobs. Not installed by me - `launchctl load` is a
system-level change, left for the user to trigger deliberately.
- Still manual, not on this scheduler: Calendar, Docs, and local-files
  ingestion. Could be added to the same 10-minute job or their own
  cadence if wanted.

### 9. Follow-up tracking: surface unresolved past questions in the digest
Nothing today remembers past questions at all — `query` is one-shot and
stateless, no history is persisted anywhere. Requested: if the user asked
something like "did I get a reply about X" and it's still unresolved, the
next digest should call that out with emphasis.
What it'd take:
- A query-history store (new - doesn't exist in any form today).
- A way to classify which past questions represent "waiting on something"
  vs. a plain fact lookup - not obvious how to do reliably without either
  an explicit "remind me about this" flag from the user, or an LLM
  judgment call on every question asked (cost/complexity tradeoff to
  discuss).
- A way to check new incoming data against an open question to decide if
  it's now resolved.
- Wiring the result into `digest/gather.py` so it can be woven into the
  next digest with the "call this out" emphasis the digest prompt already
  supports for anomalies.

### 10. Reminder/task intake + proactive scheduling suggestions
Requested: "remind me to meet with Nick" should be recognized as a task
(not a question), and a future digest (or immediate response) should
propose a specific free time slot from the calendar for approval.
What it'd take:
- A new intake path distinct from `query` (which only answers questions)
  and `digest` (which only summarizes) - recognizing an imperative
  statement as a task to track, not something to search-and-answer.
- A persisted reminders/tasks store (new).
- Free/busy computation against the already-ingested calendar data
  (straightforward - the data's there) to find open slots.
- A proposal-and-approval step consistent with the project's "nothing acts
  autonomously" principle - suggest, don't book.

### 11. Digest includes drafted emails, approvable/rejectable/editable per item — NEEDS A DECISION FIRST
Requested: the digest should come with drafted email replies, each
individually approvable, rejectable, or editable.
**Flagging before any implementation**: drafting is straightforward
(Claude can write a reply given context, same mechanism as answer
generation). But *sending* an approved draft requires giving Meridian a
brand-new Google OAuth scope (`gmail.send` or `gmail.compose`) on top of
the 4 read-only scopes (`gmail.readonly`, `calendar.readonly`,
`documents.readonly`, `drive.readonly`) it has today. Every design
principle in `CLAUDE.md` and the README so far is built around "read-only,
nothing ever sends or executes on its own" - "approval means accepting the
digest itself, not authorizing an outbound action" is stated explicitly in
the Phase 10 README section. This would be the first time that stops being
true. Also needs per-item approval granularity in the digest review flow
(today's `digest review --approve/--reject` decides the whole run, not
individual items). Wants an explicit go-ahead before starting, not just
folding into a larger feature bundle.

### 12. Calendar notifications
Requested: proactive alerts (e.g. "meeting in 15 minutes"), not just
seeing upcoming events in a digest. Different from a periodic sync/digest
job - needs something checking the calendar close to real-time and firing
a native OS notification, which means either a genuinely long-running
background process or a very frequent scheduled check (e.g. every minute)
- worth scoping the tradeoff before picking an approach. Related to #5
(no consumer-facing interface) - likely shares infrastructure with a
"digest is ready" notification if #5 is ever built.

## Fixed

### 8. Digest read like a curated newsletter, not a quick status update
`digest/prompt.py`'s system prompt said "group related items together...
keep skimmable in under a minute" - pushed Claude toward thematic
categories with markdown headers, bold titles, and emoji section icons
(📚🎓🎁⏰), reading like a blog digest rather than a personal heads-up.
Rewrote the prompt: plain prose, no markdown/emoji, organized by source
(calendar, email, docs, notes) not topic, one line for "nothing new"
sources instead of silent omission, routine noise (newsletters) condensed
to a count instead of listed item-by-item, and anomalies (unusual charges,
security alerts, stalled threads) called out directly.

### 7. Digest crashes on first run after any full backfill (prompt too long)
`digest/gather.py` asks each source's store for "what's new since `since`."
`gmail/store.py::list_messages_since` and `local_files/store.py`'s
equivalent both filtered on `updated_at` (when the row was last written to
the *local* database) instead of the content's real-world date
(`sent_at` for Gmail, `mtime_ns` for local files). Right after any full
backfill, every row's `updated_at` is "just now," so the very first digest
run swept in the *entire* mailbox — not just genuinely recent messages —
and blew past Claude's context limit (`prompt is too long: 206771 tokens
> 200000 maximum`, hit on a real 1,198-message mailbox). `docs/store.py`
did NOT have this bug — it already correctly filters on `modified_time`,
the doc's real Google-side edit date. Fixed by filtering on the real
content timestamp instead of `updated_at`, matching what `docs/store.py`
already did correctly.

### 2. Network timeouts crash the whole sync instead of retrying
`common/google_api.py`'s `execute_with_retry` only retried `RateLimitedError`
and `TransientHttpError` — a raw connection-level timeout (no HTTP response
at all) isn't either of those, so it wasn't retried and crashed the entire
ingestion run. Found via a real Gmail full-backfill that died on a single
message's `TimeoutError` mid-sync. Fixed by catching `TimeoutError`/
`ConnectionError` and retrying them the same way as a 5xx.

## Also found, not yet actioned

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
