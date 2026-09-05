# Backlog

Running list of known gaps and improvements found while testing Meridian
against real data, beyond the 12 core phases in `CLAUDE.md`. Add to this as
we find more. Nothing here is scheduled until explicitly picked up.

## Next up

### 1. "Upcoming/future" date filtering (recency-aware answers fixed, explicit phrase filtering still open)
Two distinct halves. **Fixed**: the answer-framing half — asking "what
flight bookings do I have" used to present an already-happened May 2026
flight with no indication it was in the past. `query/prompt.py` now
computes "(N days ago)" / "(in N days)" deterministically in code for
every dated context item (gmail `sent_at`, calendar `start_at`) instead of
asking the LLM to do date arithmetic itself - a real test showed the LLM
was unreliable at this (correctly called one past item "past" and
incorrectly called an equally-past item "upcoming" in the same response).
Real result now: correctly says "there are no upcoming flight bookings"
while still naming the most recent past one for context.

**Still open**: `query/date_range.py` still has no phrase for "upcoming,"
"next week," "future," anything forward-looking, in either direction - so
there's no way to explicitly ask retrieval to filter to *only* future
items (e.g. "what's on my calendar next week"). What it'd take:
- Add forward-looking phrases to `extract_date_range()` (e.g. "upcoming,"
  "next week," "next month," "in the next N days") returning a
  present-to-future window instead of a past/current one.
- Decide how this interacts with Gmail: an email's `sent_at` is always in
  the past even when it describes a future event (e.g. a flight
  confirmation) — a true "upcoming flights" *retrieval filter* would need
  to read travel *dates mentioned in the content*, not the email's send
  date. That's a materially harder feature (structured date extraction
  from free text) — worth explicitly scoping as in/out before starting.
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

### 11. Draft replies in the user's voice, adjusted by relationship, approvable/editable — NEEDS A DECISION FIRST
Requested (as part of Inbox Intelligence): draft replies matching how the
user actually writes, adjusted by relationship to the recipient (e.g.
more formal for a manager, casual for a friend), each individually
approvable/rejectable/editable.
**Flagging before any implementation**: drafting text is straightforward
(same mechanism as `query`'s answer generation), but two real design
gaps exist before it'd be any good: (1) no "voice profile" exists - would
need to build one from the user's own past sent messages, which first
requires being able to tell sent vs. received mail apart (today's
`messages` table has no "is this from me" concept - the same
`account_email` captured for backlog #13 makes this newly possible); (2)
no "relationship to this contact" concept exists - would need inferring
from `entity_graph` (e.g. frequency/reciprocity of contact) or explicit
tagging, not obvious which without discussion.
**Separately, and more fundamentally**: *sending* an approved draft
requires giving Meridian a brand-new Google OAuth scope (`gmail.send` or
`gmail.compose`) on top of the 4 read-only scopes it has today. Every
design principle in `CLAUDE.md` and the README so far is built around
"read-only, nothing ever sends or executes on its own." This would be the
first time that stops being true. Also needs per-item approval granularity
in whatever review flow surfaces these (today's `digest review
--approve/--reject` decides a whole run, not individual items). Wants an
explicit go-ahead before starting, not just folding into a larger feature
bundle.

### 15. Merge context across threads about the same thing or person
Requested (Inbox Intelligence): recognize that several differently-subject-
lined threads are actually about the same topic or person, and merge that
context.
What it'd take:
- For "same person": `entity_graph` (Phase 9) already does cross-source
  identity resolution - this part may already be substantially covered,
  worth checking against real data before building anything new.
- For "same topic" (e.g. three threads with different subjects that are
  all actually about the Q3 budget): a genuinely new capability - topic
  clustering/deduplication across threads, not just entity identity. No
  existing mechanism in this codebase does this; would need real scoping
  (embedding-similarity clustering? LLM-judged? at what threshold?) before
  starting.

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

### 16. Digest surfaced promotional email instead of just the primary inbox
Requested: exclude promotional emails from the digest, "basically primary,
based on priority." `digest/gather.py` now excludes gmail's own
CATEGORY_PROMOTIONS/SOCIAL/UPDATES/FORUMS labels (reusing the
`NON_ACTIONABLE_CATEGORIES` concept already built for
inbox_intelligence's stale-threads/commitments) and sorts what remains
so IMPORTANT-labeled mail comes first.

Real test against a real pending digest (3 promotions + a LinkedIn
invitation + an Uber feedback request) surfaced a real tradeoff before
finalizing: the LinkedIn invitation is tagged CATEGORY_SOCIAL, not
CATEGORY_PROMOTIONS - a strict 4-category exclusion removes it too, not
just the ads. Confirmed with the user this is the intended behavior
(strict Primary-tab match, not "ads only") before shipping it.

### 14. Soft-commitment tracking ("I'll send this by Friday" → trackable follow-up)
Second piece of Inbox Intelligence. `python -m meridian.inbox_intelligence
scan-commitments` (costs real LLM usage, bounded by `--limit`) detects a
promise the SENDER of an email makes about their own future action, and
converts it into a trackable follow-up; `commitments` lists open ones
(free); `resolve-commitment <id>` marks one done manually.

Scoped narrower than originally requested: only self-commitments made by
whoever wrote the email are tracked (covers both directions across a
mailbox, since the account owner appears as sender on outgoing mail and
as recipient on incoming mail) - not a general "did anyone commit to
anything anywhere in this thread" pass. There is no automatic
fulfillment-detection (checking whether a matching reply/attachment
actually showed up) - `resolve-commitment` is manual only. Still overlaps
conceptually with #9 (follow-up tracking on the user's own past
questions) - not yet unified into one system.

Guardrails from the start: every message is redacted
(`tokenize_for_external_call`) before the LLM call and untokenized after,
and every call records an `llm.external_call` audit event. Learned from
the query-recency fix (item 1, above) that LLM date arithmetic is
unreliable, so the LLM only extracts the deadline phrase verbatim (e.g.
"by Friday") and `deadlines.py::resolve_deadline_phrase()` resolves it to
an actual date deterministically in code, anchored to the message's real
`sent_at` - unrecognized phrases return no due date rather than guessing.

Real smoke test against real mail found and fixed two concrete bugs: the
LLM's literal "NONE" deadline output was being stored as that string
instead of NULL, and a plain request ("please update the tracker") was
misclassified as a commitment despite the prompt already saying not to
count requests - tightened the prompt to explicitly test "did the sender
promise to act themselves, not the recipient." Final real result after
both fixes: 6 → 4 commitments, all genuine. Known remaining gap: absolute
date references in prose ("around the 9th of September") aren't resolved
to a due date - the deterministic resolver only handles weekday names and
relative-day phrases (tomorrow, next week, in N days, etc.), correctly
leaving those as "no due date" rather than guessing.

### 13. Inbox Intelligence: stale-thread detection ("your move")
First piece of Inbox Intelligence (the "really good RAG + reminders" track,
separate from the digest). `python -m meridian.inbox_intelligence
stale-threads` lists Gmail threads where the last message wasn't from the
account owner and it's been quiet for 3+ days (`--min-days` to change).
Needed the account's own email address, which nothing captured before -
now grabbed for free from the `getProfile` call gmail sync already makes,
self-healing on the very next sync (full or incremental) for
already-populated databases, no `--full-resync` required. New
`gmail/store.py::list_latest_message_per_thread()` groups by `thread_id`
and takes the max `sent_at` per thread; new
`inbox_intelligence/stale_threads.py::find_stale_threads()` filters out
threads where the account owner sent the last message and applies the
staleness threshold. Real smoke test against 1,208 real messages found
574 "stale" threads, many 7+ years old; excluding gmail's
CATEGORY_PROMOTIONS/SOCIAL/UPDATES/FORUMS labels and adding `--max-days`
brought it to 3 genuine ones, but 2 of those 3 turned out to be automated
visa-processing auto-replies (no CATEGORY_* label catches those since
they land in the primary inbox) - added a subject/sender heuristic (Auto
Reply, Out of Office, Undeliverable, no-reply@, etc.) to exclude those
too. Final real result: 574 -> 1, the one genuine thread.

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
