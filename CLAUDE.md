# CLAUDE.md

Guidance for Claude Code when working in this repository (Meridian).

## What this is

Meridian is a local-first personal knowledge assistant. It connects to Gmail,
Google Calendar, and Google Docs (read-only OAuth, single consent flow) plus a
local folder of notes/meeting transcripts, redacts PII before anything leaves
the machine, builds a hybrid (vector + keyword) index, answers questions with
citations back to exact sources, and runs a scheduled digest job whose output
always goes into a human approval queue — nothing sends or executes on its
own.

## Core principles (apply to every phase)

- **Local-first**: raw personal data never leaves the machine; only redacted,
  summarized text goes to external APIs.
- **Grounded, not hallucinated**: every claim cites its exact source.
- **Human-gated**: nothing acts autonomously; all actions require explicit
  approval.
- **Incremental**: never reprocess unchanged data — Gmail History API,
  Calendar sync tokens, Docs revision IDs, content hashes for local files.
- **Production-rigor**: retries with exponential backoff, dead-letter
  handling (log and skip, never crash the run), idempotent processing,
  proactive self-throttling (not just reacting to 429s), correct rate-limit
  handling (respect `Retry-After`), structured logging (timestamp, module,
  operation, status, duration — no `print`), and observability/metrics for
  key operations.

## Build order (each phase independently testable)

1. `auth/` — Google OAuth setup, encrypted token storage with auto-refresh
2. `ingestion/gmail/` — polling + History API incremental sync, pagination, throttling
3. `ingestion/calendar/` — polling + sync tokens
4. `ingestion/docs/` — polling + revision tracking
5. `ingestion/local_files/` — folder watcher, content-hash change detection
6. `redaction/` — PII scrubbing, applied uniformly across all sources
7. `indexing/` — structure-aware chunking, local embeddings, hybrid search
8. `query/` — retrieve, rerank, generate grounded answers with citations
9. `entity_graph/` — entity extraction, cross-source linking
10. `digest/` — LangGraph stateful workflow with human-in-the-loop approval
11. `security/` — audit logging, scoped API keys, encrypted local storage, input validation, dependency scanning
12. `tests/` — eval harness, golden Q&A set, retrieval scoring

## How we work together

- Build in small steps. After each meaningful chunk (a working function, a
  tested module, one phase), stop and explain in plain language what was
  built and why — don't batch unrelated pieces into one silent pass.
- Commit to git in small, meaningful increments — one coherent piece of work
  per commit, with a clear message.
- Don't move on to the next phase until the user has confirmed they
  understand the current one.
- Phases are directed step by step by the user, not front-run.
