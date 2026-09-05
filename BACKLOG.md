# Backlog

Running list of known gaps and improvements found while testing Meridian
against real data, beyond the 12 core phases in `CLAUDE.md`. Add to this as
we find more. Nothing here is scheduled until explicitly picked up.

## Next up

### 18. Fold stale threads / open commitments into the daily digest
Requested alongside the router (#17): the digest should also mention
threads needing approval and open commitments, not just new
activity/upcoming calendar. Not built yet - `digest/gather.py` would need
to call `find_stale_threads()`/`InboxIntelligenceStore.list_open_commitments()`
and fold the results into `GatheredItem`s (or a dedicated section), likely
reusing the same "summarize, don't dump raw text" approach `query/router.py`
already uses for the same data.

### 11 (remaining half). Actually sending an approved draft — NEEDS EXPLICIT GO-AHEAD
The drafting half is built (see Fixed, below) - what's left is a send
path. Requires giving Meridian a brand-new Google OAuth scope
(`gmail.send` or `gmail.compose`) on top of the 4 read-only scopes it has
today. Every design principle in `CLAUDE.md` and the README so far is
built around "read-only, nothing ever sends or executes on its own" -
this would be the first time that stops being true. Deliberately not
started without explicit go-ahead (given, but not yet acted on - waiting
on the user to grant the new OAuth scope first). Also still needs
per-item approval granularity wired into whatever review flow surfaces
these (today's `digest review --approve/--reject` decides a whole run,
not individual items) - `replies/store.py::DraftStore.approve()` today
only flips a status flag, there's genuinely nothing downstream that acts
on it yet.


## Fixed

### 22. No way to ask a follow-up question with context from the prior one
Requested: "how do we create a text thread where I can ask follow up
questions?" Every query was fully stateless - `ask()` had no memory
between invocations, so "what about next month" (after asking about this
month) had nothing to resolve "next month" against and would fail
retrieval on its own.

New `conversation/` module: `store.py::ConversationStore` persists a
thread's turns as plain real text (never a redaction mapping - mappings
stay per-call and are never persisted, per this project's existing
redaction design; each turn just gets folded into the same single
prompt string and re-redacted fresh on every call, like everything
else). `followup.py::rewrite_followup_question()` is the piece that
actually makes retrieval work on a bare follow-up: one small Claude call
expands "what about next month" into a standalone, retrievable question
using the thread's recent turns, before embedding/retrieval ever runs -
skipped entirely (no LLM call) when the thread has no history yet.
`query/answer.py::ask()` gained optional `conversation_id`/
`conversation_store` params (default `None`, same pattern as every
other optional store in this project) - wired into
`python -m meridian.query "<text>" --thread <name>`; omit `--thread` for
the original one-shot, stateless behavior.

Scoped deliberately narrow for now: only the GENERAL/fact-question path
(`ask()`) is conversation-aware, not the other six router intents
(stale threads, commitments, resolve, broad summary, reminders, drafts) -
those remain one-shot. History is a simple fixed window (last 10 turns),
not a summarization strategy, so a very long-running thread loses its
earliest context rather than the prompt growing without bound. An
abstained turn isn't recorded into the thread (only a successful answer
is), so a follow-up to an abstain has nothing to reference.

Also has its own CLI (`python -m meridian.conversation list/clear
<thread>`) as a direct escape hatch.

Verified against real data end to end: asked "any upcoming flight
bookings" in a thread, then "what was the booking reference again?" as a
genuine bare follow-up with no meaning on its own - correctly answered
"XHQS83" by resolving it against the prior turn.

### 20. Reranker under-scored genuinely correct matches, causing wrong abstains
Found via real testing: "any upcoming flight bookings" and a laptop
drop-off question both abstained ("nothing confident enough") even
though the correct answer existed and was already ranked #1 by hybrid
search. Traced to the local cross-encoder (`ms-marco-MiniLM-L-6-v2`)
scoring the correct top candidate far below the 0.5 abstain threshold
(confidences of 0.006-0.03) when the question's phrasing shares little
vocabulary with the source text (typos, paraphrasing, casual wording) -
a real, recurring pattern, not a one-off.

Rather than a second, heavier reranker model (likely the same
vocabulary-matching blind spot, just a bigger version of it), added
`query/answer.py::_llm_confirms_relevance()` - a last-resort Claude call,
only spent on the already-rare abstaining path (never on a confident
answer), asking whether the single top-ranked candidate genuinely
answers the question. Reuses the same "ask the LLM to judge instead of
guessing" pattern already used throughout this project (commitment
filtering, resolve-matching, reminder-matching) rather than adding a new
ML dependency. If confirmed, the answer is generated from just that one
chunk (not the full unfiltered pool, to avoid reintroducing noise).

Verified against real data: "any upcoming flight bookings" now correctly
answers "no upcoming flights, but your last one was [date]" instead of
abstaining; the laptop drop-off question now correctly answers with
when/where/how, citing the real thread. A third real failure found in
the same session ("what is my CV profile") turned out to be a different,
deeper issue - see #21, not fixed by this change.

### 1. "Upcoming/future" date filtering
Two distinct halves, both now fixed. The answer-framing half: asking
"what flight bookings do I have" used to present an already-happened
flight with no indication it was in the past. `query/prompt.py` now
computes "(N days ago)" / "(in N days)" deterministically in code for
every dated context item (gmail `sent_at`, calendar `start_at`) instead of
asking the LLM to do date arithmetic itself - a real test showed the LLM
was unreliable at this (correctly called one past item "past" and
incorrectly called an equally-past item "upcoming" in the same response).

The retrieval-filtering half: `query/date_range.py` had no phrase for
"upcoming," "next week," anything forward-looking, so there was no way to
explicitly filter retrieval to *only* future items. Added forward-looking
counterparts alongside the existing backward-looking ones: "next week,"
"next month" (with year rollover), "next year," "next N days," "next
<weekday>" (the next occurrence strictly ahead, not today even if today
is that weekday), and a bare "upcoming" (30-day default window) -
inserted alongside their existing backward equivalents, same function
structure. Calendar's `start_at` is a genuinely forward-dated field so
this is a clean filter there; an email's `sent_at` is always in the past
even when its *content* describes a future event (e.g. a flight
confirmation) - reading travel dates out of message content would be a
separate, materially harder feature, intentionally out of scope here.

### 3. No scheduler — nothing runs automatically
Every command (ingestion, indexing, digest) was one-shot, run-by-hand
only. `scripts/install_launchd.sh` installs macOS `launchd` agents
covering every source, not just Gmail: `scripts/sync_all.sh` (renamed
from `sync_gmail.sh`) runs Gmail, Calendar, and Docs ingestion
unconditionally every 10 minutes, and local-files ingestion
conditionally (skipped gracefully, not erroring the whole job, when
`MERIDIAN_NOTES_FOLDER` isn't set in `.env`), then reindexes everything
incrementally. `DIGEST_DAYS` in `.env` restricts which days the digest
actually runs (comma-separated 3-letter day names, e.g. `mon,wed,fri`;
empty = every day) - checked by `scripts/nightly_digest.sh` itself, not
baked into the plist, so it's a config setting rather than the "when the
user logs in" login-screen concept originally requested (there's no
login/account system in this local single-user tool for that to mean
anything). `./scripts/uninstall_launchd.sh` removes the jobs (and cleans
up the old Gmail-only job name if present from before this fix). Not
installed automatically - `launchctl load` is a system-level change, left
for the user to trigger deliberately.

### 4. `query` couldn't handle broad/open-ended asks
Questions like "summarize my recent emails" or "what's been happening
lately" structurally couldn't be answered by the fact-lookup retrieval
path (it scores individual small chunks against the question - no single
chunk is "about" a broad meta-question, so it correctly abstained rather
than hallucinate). Added a 5th router intent, BROAD_SUMMARY, alongside
the original four from #17 - it reuses `digest/gather.py::gather_items()`
wholesale rather than reimplementing "gather recent items," which had the
side benefit of inheriting #16's promotional-filtering fix and #19's
digest-tone rewrite "for free," since both live in the code being reused.
Honors a recognized date phrase in the question itself (thanks to #1
above); otherwise defaults to a 7-day lookback, same philosophy as
digest's own lookback-hours default. Falls through to `general` (not an
error) if the caller hasn't wired up the four stores this needs
(calendar/docs/notes/entity) - same pattern as every other optional
router dependency.

### 19. Commitment scanner flagged boilerplate SLA text as a real promise
Requested: an email about a hotel booking from 2 months ago was coming in
as a tracked commitment - needed a better filter. Root cause wasn't
really about hotel bookings: the hotel's confirmation email had a
standard boilerplate line ("we acknowledge emails within 2 hours during
business hours, 9am-6pm") which is generic policy text applied to every
customer, not a specific promise made in response to this exchange.
Tightened `commitment_prompt.py` to explicitly exclude that pattern - the
test is now "did the sender promise, specifically and in response to
something in THIS exchange, to personally do something" vs. a standing
policy/SLA statement. Verified against real data: the two boilerplate-SLA
false positives are gone, the remaining commitments are all genuine.

Followed up with a deterministic backstop, since LLM judgment alone is
stochastic: `commitments.py::_looks_like_boilerplate_policy()` rejects
any candidate whose description/deadline phrase matches known SLA
language ("business hours," "typically respond within," "standard
response time") regardless of what the LLM said - the reliable tell
being that policy text describes a *recurring turnaround window*, not a
deadline tied to this specific exchange. Verified this catches it even
when a fake LLM is forced to say yes to boilerplate text.

Also: `digest/gather.py` gained a synthetic count item ("N additional
email(s) arrived in Promotions/Social/Updates/Forums") since the digest
now fully excludes those categories (#16) and had no way left to mention
how many arrived - requested separately, alongside #16.

### 15. Merge context across threads about the same thing or person
Requested (Inbox Intelligence): recognize that several differently-subject-
lined threads are actually about the same topic or person, and merge that
context. "Same person" was already covered by `entity_graph` (Phase 9)'s
cross-source identity resolution. "Same topic" needed a genuinely new
capability - and a flat entity/lookup table wasn't enough for it (per
explicit correction while scoping this): it needed real graph nodes and
edges so cross-item context can be *traversed*, not just joined.

Built a small generic graph directly in `entity_graph/store.py`, additive
to the existing `entities`/`entity_mentions` tables, not a replacement:
- `topics` table: a topic node (`topic_id`, a short LLM-generated `label`,
  and an embedding).
- `graph_edges` table: typed, directional edges between plain string node
  references (`item:<source>:<id>`, `topic:<topic_id>`) - a node reference
  is just a string rather than a foreign key into one specific table, so
  one table covers edges between any two node kinds without a join table
  per combination.
- `EntityGraphStore.items_sharing_topic_with(source, item_id)`: a real
  2-hop graph traversal (item -> topic -> other items) - a plain lookup
  against edges already recorded, not a fresh similarity computation on
  every call.

New `entity_graph/topic_graph.py::link_item_to_topic()` links one item to
a topic node: brute-force cosine similarity (reusing
`indexing/vector_search.py::cosine_similarity_top_k`, the same approach
already used for retrieval) against existing topic embeddings first - if
one is a close enough match (similarity >= 0.6), reuse it; otherwise mint
a new topic node labeled by one Claude call. New
`orchestrator.py::run_topic_pass()` mirrors `run_ner_pass()`'s incremental
per-item structure (change-signal tracking, stale-item cleanup, a failing
item logged and skipped rather than crashing the run) using each item's
first indexed chunk as its representative text/embedding.

Costs a real LLM call per not-yet-linked item, so - unlike the rest of
`entity_graph`'s free default run - this is opt-in via
`python -m meridian.entity_graph --link-topics`. Verified against real
data: a local note about an upcoming Lisbon trip was correctly labeled
"Lisbon October trip planning" and linked; a re-run correctly skipped it
as unchanged with no further LLM call.

### 9. Follow-up tracking: surface unresolved past questions in the digest
Requested: if the user asked something like "did I get a reply about X"
and it's still unresolved, the next digest should call that out with
emphasis. Nothing remembered past questions at all before this - `query`
was one-shot and stateless.

Built `query/history_store.py::QueryHistoryStore` (new `data/query/
query_history.db`) recording every question asked through `query`'s CLI.
The "waiting on something vs. plain fact lookup" classification (open
question from the original scoping) is one small Claude call per question
(`query/history.py::record_question`) - reliable enough, and far cheaper
than building a separate explicit-flag UX for a one-shot CLI. Checking
whether an open question is now resolved (`check_open_questions`) reuses
`query.answer.ask()` wholesale rather than inventing new retrieval logic:
re-ask the question against the current index, and if a confident (non-
abstained) answer comes back, one more small Claude call judges whether
it actually indicates the awaited thing happened (RESOLVED) or the answer
doesn't really settle it (PENDING) - an abstain or a PENDING verdict both
leave the question open.

Wired into `digest/graph.py`'s `gather()` node (optional `history_store`/
`ask_fn` params, both `None` by default so existing digest callers/tests
are untouched): a still-open question becomes a `GatheredItem` sourced
`query_history`, and `digest/prompt.py`'s system prompt now explicitly
requires any such item to always be mentioned, never folded into a
routine-noise count. `digest/__main__.py`'s `run` command builds the
index/embedder/reranker this needs and binds them into `ask_fn` via
`functools.partial` - the same pipeline a direct query would use, not a
parallel implementation. A resolved question is marked resolved silently
(a digest reports what's pending, not closure confirmations) and dropped
from the gathered items entirely.

Verified against real data end to end: asked "did I get a reply about
the Lisbon trip" (correctly classified as waiting, no confident answer
existed yet), then ran a real digest - it re-checked the question, still
found nothing, and opened with "You're still waiting on a reply about the
Lisbon trip that you asked about just now, and we don't have a confident
answer for you yet [1]," citing the follow-up item by source.

### 10. Reminder/task intake + proactive scheduling suggestions
Requested: "remind me to meet with Nick" should be recognized as a task
(not a question), and a future digest (or immediate response) should
propose a specific free time slot from the calendar for approval.

Added a 6th router intent, REMINDER, alongside the other five from #17 -
the same "everything is a text message" entry point, not a separate
intake surface. New `reminders/store.py::ReminderStore` (`data/reminders/
reminders.db`) persists the raw reminder text plus whatever slot got
proposed; new `reminders/scheduling.py::propose_free_slot()` is a
deterministic interval-scan (existing calendar events as busy blocks,
business hours 9-5 on weekdays, first open gap of the requested duration
over the next week) - no LLM guessing at times, the same lesson already
applied to date-range parsing and commitment deadlines elsewhere in this
project. The router's existing RESOLVE intent was extended to also match
against pending reminders, so "the Nick reminder is done" dismisses it the
same way a thread or commitment gets dismissed. There's no calendar-write
path anywhere in this project (read-only OAuth, per CLAUDE.md), so
"propose, don't book" isn't just a policy choice here - there's structurally
nothing to book with; the reminder's job ends at proposing a slot.

Also has its own CLI (`python -m meridian.reminders add/list/dismiss`) as
a direct escape hatch, mirroring `inbox_intelligence`'s CLI-alongside-router
pattern.

Verified against real data end to end: "remind me to meet with Nick"
correctly classified as REMINDER, recorded, and proposed a real open slot
from the actual calendar; "mark the accountant reminder as resolved"
correctly matched and dismissed it via the router's RESOLVE path.

### 12. Calendar notifications
Requested: proactive alerts (e.g. "meeting in 15 minutes"), not just
seeing upcoming events in a digest. Scoping this required picking between
a genuinely long-running background process and a very frequent scheduled
check - went with the latter: a one-shot `python -m meridian.notifications
check` invoked every minute via a new launchd job
(`com.meridian.calendarnotify`, `StartInterval` 60), consistent with this
project's existing architecture where every phase is a one-shot CLI
scheduled externally, not an in-process daemon. A genuine daemon would
need its own process supervision, crash-restart, and log-rotation
handling for a single-user personal tool - not worth it just to shave the
alert lead time from "within the last minute" to "instant."

New `notifications/calendar_watch.py::check_upcoming_events()` finds
events starting within a configurable lead time (default 15 min,
`CALENDAR_NOTIFY_LEAD_MINUTES` in `.env`) that haven't been notified about
yet, and `notifications/store.py::NotificationStore` (`data/notifications/
notifications.db`) dedupes across the once-a-minute checks so the same
event doesn't re-alert every minute between the lead time and its actual
start. `notifications/notifier.py::send_native_notification()` fires a
real macOS notification via `osascript` - no extra dependency, ships with
every Mac - with the event summary escaped before interpolation into the
AppleScript literal. All-day events are excluded ("starts in 15 minutes"
doesn't mean anything for them).

`scripts/install_launchd.sh`/`uninstall_launchd.sh` updated to install/
remove the new job alongside auto-sync and the nightly digest. Verified
against real data: `send_native_notification()` fired a genuine macOS
notification banner; `python -m meridian.notifications check` ran
correctly against the real calendar (0 events in the next 30 days, so 0
notifications - confirmed correct by checking the raw calendar data
directly, not just trusting the "0" output).

Related to #5 (no consumer-facing interface) - would share infrastructure
with a "digest is ready" notification if #5 is ever built.

### 11 (drafting half). Draft replies in the user's voice, adjusted by relationship
Requested (as part of Inbox Intelligence): draft replies matching how the
user actually writes, adjusted by relationship to the recipient,
approvable/rejectable/editable. Built the drafting half only, by explicit
request - the sending half stays a separate, not-yet-authorized piece of
work (see Next up, above).

New `replies/` module:
- `replies/voice.py::sample_voice_examples()` - not a trained "voice
  model," just the user's own most recent substantive sent messages
  (skipping trivial one-liners like "Thanks!") handed to the LLM as
  few-shot style examples. Telling sent vs. received mail apart uses the
  `account_email` already captured for #13/#3.
- `replies/relationship.py::classify_relationship()` - a deterministic
  count of past messages exchanged with the contact (either direction),
  bucketed into new/occasional/frequent. Deliberately not an LLM
  judgment - same "prefer reliable code over LLM guessing" approach this
  project already applies to dates and deadlines. The message currently
  being replied to is excluded from its own count, or a genuine
  first-time contact could never register as "new."
- `replies/drafting.py::draft_reply_for_message()` - combines both
  signals into one Claude call, redacted per the usual pattern, and
  stores the result via `replies/store.py::DraftStore`.
- Router got a 7th intent, DRAFT_REPLY, matching a request like "draft a
  reply to Alice's email" against threads currently awaiting a reply
  (`find_stale_threads()` - the same set #17's RESOLVE already matches
  against), reusing the same "match request to one candidate via an LLM
  call, ask for clarification rather than guess wrong" approach.
- Own CLI (`python -m meridian.replies draft/list/show/edit/approve/reject`)
  as a direct escape hatch, same pattern as reminders/inbox_intelligence.

`DraftStore.approve()` only flips a status flag - there is no send path
anywhere in this codebase for it to trigger, by design (see Next up,
above). Verified against real data: drafted a reply to a real stale
thread (a shipping company's booking confirmation) that correctly
referenced specific real details from the original email (a £10 missed-
collection charge, label/documentation requirements) rather than
generic filler; a second draft, generated through the full router path
against a different real thread, correctly matched the thread by name
and produced a reply signed with the user's own real name - picked up
from the voice examples, not invented.

### 17. Natural-language router: "everything is a text message"
Requested: instead of separate CLI subcommands per capability, a single
text message should map to whichever backend actually answers it - "any
thread needs my approval" should surface stale threads, without the user
needing to know `stale-threads` exists as a command. `python -m
meridian.query` now runs every question through `query/router.py` first
(one cheap Claude call to classify into stale_threads / commitments /
resolve / general) before falling through to the unchanged `ask()`
pipeline for genuine fact questions.

- **stale_threads**: summarizes in prose, never dumps the raw email
  (per this same request's other ask) - the model describes each
  thread in its own words and only quotes the message if the user's
  question explicitly asks to see it. Capped to a 30-day window by
  default (unbounded would resurface the same hundreds-of-ancient-
  threads problem #13 already fixed for the standalone CLI command -
  a real test on this router caught it doing exactly that, citations
  up to [170], before the cap was added).
- **commitments**: formatted directly, no extra LLM call - a
  commitment's description is already a distilled fact from extraction
  time, not raw text needing summarizing.
- **resolve**: matches the user's message against combined open
  threads + commitments via one more Claude call, then dismisses/
  resolves whichever matched, or asks for clarification rather than
  guessing when ambiguous - confirmed for real: "the billy wardrop
  thread is resolved" was correctly treated as ambiguous (the same
  email produced both a stale-thread entry and a commitment entry) and
  asked for clarification instead of guessing wrong; "mark the laptop
  drop-off commitment as done" correctly matched and persisted.

New `InboxIntelligenceStore.dismiss_thread()` gives stale threads the
same persisted resolved-state commitments already had (previously
stale-threads had zero persistence - purely computed live every call).
`CommitmentStore` renamed to `InboxIntelligenceStore` to reflect that.

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

### 5. No consumer-facing interface
CLI-only today — no chat window. Native calendar notifications exist now
(#12); a chat window backend piece exists now too (#22's
`ConversationStore` + follow-up rewriting - a UI just needs to call
`query.answer.ask()` with a `conversation_id` per open chat window). The
UI itself is still not built, and the "installable by a non-technical
person" problem (bigger, includes OAuth consent-screen verification
concerns) is untouched.

### 6. Cosmetic: HuggingFace Hub warning on every query
`sentence-transformers` prints "You are sending unauthenticated requests to
the HF Hub..." on every run. Harmless (models are already cached locally),
but noisy. Fix: `export HF_HUB_OFFLINE=1`, or bake a quiet default into the
code once models are confirmed cached.

### 21. Retrieval sometimes never surfaces the right document as a candidate at all
Found while verifying #20's reranker tiebreak fix: "what is my CV
profile" still abstains, but for a different reason than #20's fixed
cases. The actual "Suhana Grewal - CV" Google Doc (with the real PROFILE
section text) never even makes it into the top-5 reranked candidates for
that phrasing - two unrelated Gmail messages that merely mention "CV" in
passing, and two completely unrelated docs, rank above it. #20's LLM
tiebreak only ever examines the single top-ranked candidate, so it can't
help when the right document was never retrieved as a candidate in the
first place - this is a hybrid-search/embedding recall gap, not a
confidence-threshold problem. Not scoped or fixed yet; would need
investigating why the doc's embedding doesn't surface for this phrasing
(chunking? embedding model choice? hybrid fusion weighting?) before
attempting a fix.
