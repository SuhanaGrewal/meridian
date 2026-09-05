from datetime import datetime, timezone

from meridian.entity_graph.store import EntityGraphStore
from meridian.inbox_intelligence.store import InboxIntelligenceStore
from meridian.ingestion.calendar.store import CalendarStore
from meridian.ingestion.docs.store import DocsStore
from meridian.ingestion.gmail.message_parser import ParsedMessage
from meridian.ingestion.gmail.store import GmailStore
from meridian.ingestion.local_files.store import NotesStore
from meridian.query.router import classify_intent, route

_ACCOUNT_EMAIL = "me@example.com"
_NOW = datetime(2024, 6, 10, tzinfo=timezone.utc)


def _message(message_id, thread_id, sender, sent_at, body_text="hello", subject="Subject") -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id, thread_id=thread_id, subject=subject, sender=sender,
        recipients=["someone@example.com"], sent_at=sent_at, body_text=body_text,
        label_ids=["INBOX"], content_hash=f"hash-{message_id}",
    )


class _FakeAnalyzer:
    def analyze(self, text, entities, language):
        return []


class _FakeMessages:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._replies.pop(0))


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeClient:
    def __init__(self, replies):
        self.messages = _FakeMessages(replies)


def test_classify_intent_stale_threads():
    client = _FakeClient(["STALE_THREADS"])

    intent = classify_intent("any threads need my approval", client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer())

    assert intent == "stale_threads"


def test_classify_intent_commitments():
    client = _FakeClient(["COMMITMENTS"])

    intent = classify_intent("what do I owe people", client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer())

    assert intent == "commitments"


def test_classify_intent_resolve():
    client = _FakeClient(["RESOLVE"])

    intent = classify_intent("mark that resolved", client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer())

    assert intent == "resolve"


def test_classify_intent_unrecognized_defaults_to_general():
    client = _FakeClient(["something unexpected"])

    intent = classify_intent("what's the weather", client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer())

    assert intent == "general"


def test_route_general_intent_returns_none_answer_for_caller_fallback(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    client = _FakeClient(["GENERAL"])

    result = route(
        "what did the budget email say", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert result.intent == "general"
    assert result.answer is None
    assert len(client.messages.calls) == 1  # only the classify call


def test_route_stale_threads_summarizes_via_second_llm_call(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-05T00:00:00+00:00"))
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    client = _FakeClient(["STALE_THREADS", "Alice is waiting to hear back from you about something [1]."])

    result = route(
        "any threads need my approval", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert result.intent == "stale_threads"
    assert result.answer == "Alice is waiting to hear back from you about something [1]."
    assert len(client.messages.calls) == 2


def test_route_stale_threads_with_no_threads_skips_second_llm_call(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    client = _FakeClient(["STALE_THREADS"])

    result = route(
        "any threads need my approval", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert result.answer == "No threads are waiting on your reply right now."
    assert len(client.messages.calls) == 1


def test_route_stale_threads_excludes_dismissed_thread(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-05T00:00:00+00:00"))
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    inbox_store.dismiss_thread("t1")
    client = _FakeClient(["STALE_THREADS"])

    result = route(
        "any threads need my approval", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert result.answer == "No threads are waiting on your reply right now."


def test_route_stale_threads_excludes_ancient_threads_by_default(tmp_path):
    """a mailbox's full history can hold hundreds of multi-year-old
    threads - routing shouldn't dump all of that into the summarization
    prompt just because the user asked in plain language instead of using
    --max-days themselves."""
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2020-01-01T00:00:00+00:00"))
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    client = _FakeClient(["STALE_THREADS"])

    result = route(
        "any threads need my approval", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert result.answer == "No threads are waiting on your reply right now."


def test_route_without_account_email_returns_explanatory_message(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    client = _FakeClient(["STALE_THREADS"])

    result = route(
        "any threads need my approval", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=None, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert "gmail" in result.answer.lower()
    assert len(client.messages.calls) == 1


def test_route_commitments_formats_without_a_second_llm_call(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    inbox_store.add_commitment(
        message_id="m1", thread_id="t1", made_by="other", other_party="alice@example.com",
        description="Alice will send the report", deadline_phrase="by Friday", due_date="2024-06-14",
    )
    client = _FakeClient(["COMMITMENTS"])

    result = route(
        "what do I owe people", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert result.intent == "commitments"
    assert "Alice will send the report" in result.answer
    assert len(client.messages.calls) == 1


def test_route_commitments_empty_message(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    client = _FakeClient(["COMMITMENTS"])

    result = route(
        "what do I owe people", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert result.answer == "No open commitments right now."


def test_route_resolve_dismisses_matched_thread(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-05T00:00:00+00:00"))
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    client = _FakeClient(["RESOLVE", "1"])

    result = route(
        "mark the alice thread resolved", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert result.intent == "resolve"
    assert inbox_store.is_thread_dismissed("t1") is True
    assert "Alice" in result.answer


def test_route_resolve_dismisses_matched_commitment(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    commitment_id = inbox_store.add_commitment(
        message_id="m1", thread_id="t1", made_by="other", other_party="alice@example.com",
        description="Alice will send the report", deadline_phrase="by Friday", due_date="2024-06-14",
    )
    client = _FakeClient(["RESOLVE", "1"])

    route(
        "the report commitment is done", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    open_commitments = inbox_store.list_open_commitments()
    assert not any(row["commitment_id"] == commitment_id for row in open_commitments)


def test_route_resolve_returns_clarifying_message_when_llm_is_unsure(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-05T00:00:00+00:00"))
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    client = _FakeClient(["RESOLVE", "NONE"])

    result = route(
        "mark it resolved", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert "not sure" in result.answer.lower()
    assert inbox_store.is_thread_dismissed("t1") is False


def test_route_resolve_with_nothing_open_skips_second_llm_call(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    client = _FakeClient(["RESOLVE"])

    result = route(
        "mark it resolved", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert "nothing open" in result.answer.lower()
    assert len(client.messages.calls) == 1


def _empty_broad_ask_stores(tmp_path):
    return (
        CalendarStore(tmp_path / "calendar.db"),
        DocsStore(tmp_path / "docs.db"),
        NotesStore(tmp_path / "local_files.db"),
        EntityGraphStore(tmp_path / "entity_graph.db"),
    )


def test_classify_intent_broad_summary():
    client = _FakeClient(["BROAD_SUMMARY"])

    intent = classify_intent("summarize my recent emails", client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer())

    assert intent == "broad_summary"


def test_route_broad_summary_without_gather_stores_falls_through_to_general(tmp_path):
    """calendar_store/docs_store/notes_store/entity_store are optional -
    a caller that hasn't wired them up shouldn't get an error, just the
    same fallback-to-ask() behavior as any other general question."""
    gmail_store = GmailStore(tmp_path / "gmail.db")
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    client = _FakeClient(["BROAD_SUMMARY"])

    result = route(
        "summarize my recent emails", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
    )

    assert result.intent == "general"
    assert result.answer is None
    assert len(client.messages.calls) == 1


def test_route_broad_summary_gathers_and_summarizes(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-08T00:00:00+00:00"))
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    calendar_store, docs_store, notes_store, entity_store = _empty_broad_ask_stores(tmp_path)
    client = _FakeClient(["BROAD_SUMMARY", "You got one email from Alice this week [1]."])

    result = route(
        "summarize my recent emails", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
        calendar_store=calendar_store, docs_store=docs_store, notes_store=notes_store, entity_store=entity_store,
    )

    assert result.intent == "broad_summary"
    assert result.answer == "You got one email from Alice this week [1]."
    assert len(client.messages.calls) == 2


def test_route_broad_summary_with_nothing_gathered_skips_second_llm_call(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    inbox_store = InboxIntelligenceStore(tmp_path / "inbox.db")
    calendar_store, docs_store, notes_store, entity_store = _empty_broad_ask_stores(tmp_path)
    client = _FakeClient(["BROAD_SUMMARY"])

    result = route(
        "summarize my recent emails", gmail_store=gmail_store, inbox_store=inbox_store,
        account_email=_ACCOUNT_EMAIL, client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(), now=_NOW,
        calendar_store=calendar_store, docs_store=docs_store, notes_store=notes_store, entity_store=entity_store,
    )

    assert result.answer == "Nothing relevant found for that."
    assert len(client.messages.calls) == 1
