import pytest

from meridian.ingestion.gmail.message_parser import ParsedMessage
from meridian.ingestion.gmail.store import GmailStore
from meridian.replies.drafting import MessageNotFoundError, draft_reply_for_message
from meridian.replies.store import DraftStore

_ACCOUNT_EMAIL = "me@example.com"


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


def _message(message_id, sender, body_text="Can we meet next week?", thread_id=None) -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id, thread_id=thread_id or f"t-{message_id}", subject="Meeting", sender=sender,
        recipients=[_ACCOUNT_EMAIL], sent_at="2024-06-01T00:00:00+00:00", body_text=body_text,
        label_ids=["INBOX"], content_hash=f"hash-{message_id}",
    )


def test_draft_reply_for_message_stores_a_pending_draft(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "Alice <alice@example.com>"))
    draft_store = DraftStore(tmp_path / "drafts.db")
    client = _FakeClient(["Sure, next week works for me. How's Tuesday?"])

    draft_id = draft_reply_for_message(
        gmail_store, draft_store, _ACCOUNT_EMAIL, "m1",
        client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(),
    )

    draft = draft_store.get_draft(draft_id)
    assert draft["status"] == "pending"
    assert draft["draft_text"] == "Sure, next week works for me. How's Tuesday?"
    assert draft["recipient_email"] == "alice@example.com"
    assert draft["thread_id"] == "t-m1"


def test_draft_reply_for_message_raises_for_unknown_message(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    draft_store = DraftStore(tmp_path / "drafts.db")
    client = _FakeClient([])

    with pytest.raises(MessageNotFoundError):
        draft_reply_for_message(
            gmail_store, draft_store, _ACCOUNT_EMAIL, "does-not-exist",
            client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(),
        )


def test_draft_reply_for_message_passes_relationship_signal_to_the_prompt(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    for i in range(5):
        gmail_store.upsert_message(_message(f"m{i}", "Alice <alice@example.com>"))
    gmail_store.upsert_message(_message("m-current", "Alice <alice@example.com>"))
    draft_store = DraftStore(tmp_path / "drafts.db")
    client = _FakeClient(["Draft text"])

    draft_reply_for_message(
        gmail_store, draft_store, _ACCOUNT_EMAIL, "m-current",
        client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer(),
    )

    sent_message = client.messages.calls[0]["messages"][0]["content"]
    assert "frequent contact" in sent_message
