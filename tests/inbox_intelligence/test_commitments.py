from meridian.inbox_intelligence.commitments import scan_for_commitments
from meridian.inbox_intelligence.store import InboxIntelligenceStore
from meridian.ingestion.gmail.message_parser import ParsedMessage
from meridian.ingestion.gmail.store import GmailStore

_ACCOUNT_EMAIL = "me@example.com"


def _message(message_id, thread_id, sender, sent_at, body_text="hello", label_ids=None, subject="Subject") -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id,
        thread_id=thread_id,
        subject=subject,
        sender=sender,
        recipients=["someone@example.com"],
        sent_at=sent_at,
        body_text=body_text,
        label_ids=label_ids or ["INBOX"],
        content_hash=f"hash-{message_id}",
    )


class _FakeSpan:
    def __init__(self, start, end, entity_type, score=1.0):
        self.start = start
        self.end = end
        self.entity_type = entity_type
        self.score = score


class _FakeAnalyzer:
    """no-op by default; a subclass or instance attribute can supply a
    needle to detect, mirroring tests/query/test_answer.py's pattern."""

    def __init__(self, needle=None):
        self.needle = needle

    def analyze(self, text, entities, language):
        if self.needle is None:
            return []
        index = text.find(self.needle)
        if index == -1:
            return []
        return [_FakeSpan(index, index + len(self.needle), "PERSON")]


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


class _RaisingClient:
    @property
    def messages(self):
        raise AssertionError("the llm must not be called for this message")


_NO_COMMITMENT = "HAS_COMMITMENT: no"


def test_scan_finds_a_commitment_and_resolves_deadline(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(
        _message("m1", "t1", "Alice <alice@example.com>", "2024-06-12T00:00:00+00:00", body_text="I'll send it by Friday")
    )
    commitment_store = InboxIntelligenceStore(tmp_path / "commitments.db")
    client = _FakeClient(["HAS_COMMITMENT: yes\nDESCRIPTION: Alice will send the report\nDEADLINE_PHRASE: by Friday"])

    stats = scan_for_commitments(
        gmail_store, commitment_store, _ACCOUNT_EMAIL, client, "claude-haiku-4-5", _FakeAnalyzer(),
    )

    assert stats.messages_scanned == 1
    assert stats.commitments_found == 1
    open_commitments = commitment_store.list_open_commitments()
    assert len(open_commitments) == 1
    assert open_commitments[0]["made_by"] == "other"
    assert open_commitments[0]["other_party"] == "Alice <alice@example.com>"
    assert open_commitments[0]["description"] == "Alice will send the report"
    assert open_commitments[0]["due_date"] == "2024-06-14"  # the friday on/after 2024-06-12 (a wednesday)


def test_scan_made_by_me_when_sender_is_account_email(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Me <me@example.com>", "2024-06-12T00:00:00+00:00"))
    commitment_store = InboxIntelligenceStore(tmp_path / "commitments.db")
    client = _FakeClient(["HAS_COMMITMENT: yes\nDESCRIPTION: I will send the invoice\nDEADLINE_PHRASE: tomorrow"])

    scan_for_commitments(gmail_store, commitment_store, _ACCOUNT_EMAIL, client, "claude-haiku-4-5", _FakeAnalyzer())

    open_commitments = commitment_store.list_open_commitments()
    assert open_commitments[0]["made_by"] == "me"
    assert open_commitments[0]["other_party"] == "someone@example.com"
    assert open_commitments[0]["due_date"] == "2024-06-13"


def test_scan_skips_message_with_no_commitment_but_marks_it_scanned(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-12T00:00:00+00:00"))
    commitment_store = InboxIntelligenceStore(tmp_path / "commitments.db")
    client = _FakeClient([_NO_COMMITMENT])

    stats = scan_for_commitments(gmail_store, commitment_store, _ACCOUNT_EMAIL, client, "claude-haiku-4-5", _FakeAnalyzer())

    assert stats.commitments_found == 0
    assert commitment_store.list_open_commitments() == []
    assert commitment_store.is_message_scanned("m1") is True


def test_scan_does_not_recall_the_llm_for_already_scanned_messages(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-12T00:00:00+00:00"))
    commitment_store = InboxIntelligenceStore(tmp_path / "commitments.db")
    commitment_store.mark_message_scanned("m1")

    stats = scan_for_commitments(
        gmail_store, commitment_store, _ACCOUNT_EMAIL, _RaisingClient(), "claude-haiku-4-5", _FakeAnalyzer()
    )

    assert stats.messages_scanned == 0


def test_scan_skips_promotional_category_without_calling_llm(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(
        _message(
            "m1", "t1", "Newsletter <news@example.com>", "2024-06-12T00:00:00+00:00",
            label_ids=["INBOX", "CATEGORY_PROMOTIONS"],
        )
    )
    commitment_store = InboxIntelligenceStore(tmp_path / "commitments.db")

    stats = scan_for_commitments(
        gmail_store, commitment_store, _ACCOUNT_EMAIL, _RaisingClient(), "claude-haiku-4-5", _FakeAnalyzer()
    )

    assert stats.messages_scanned == 0


def test_scan_skips_auto_reply_without_calling_llm(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(
        _message("m1", "t1", "State Dept <advanceprocessing@state.gov>", "2024-06-12T00:00:00+00:00", subject="Auto Reply")
    )
    commitment_store = InboxIntelligenceStore(tmp_path / "commitments.db")

    stats = scan_for_commitments(
        gmail_store, commitment_store, _ACCOUNT_EMAIL, _RaisingClient(), "claude-haiku-4-5", _FakeAnalyzer()
    )

    assert stats.messages_scanned == 0


def test_scan_respects_limit(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    for index in range(5):
        gmail_store.upsert_message(
            _message(f"m{index}", f"t{index}", "Alice <alice@example.com>", f"2024-06-{10 + index:02d}T00:00:00+00:00")
        )
    commitment_store = InboxIntelligenceStore(tmp_path / "commitments.db")
    client = _FakeClient([_NO_COMMITMENT, _NO_COMMITMENT])

    stats = scan_for_commitments(
        gmail_store, commitment_store, _ACCOUNT_EMAIL, client, "claude-haiku-4-5", _FakeAnalyzer(), limit=2
    )

    assert stats.messages_scanned == 2


def test_literal_none_deadline_phrase_is_stored_as_null_not_the_string_none(tmp_path):
    """the llm sometimes writes the literal word NONE instead of omitting
    the line - that must become a real NULL, not be stored verbatim."""
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-12T00:00:00+00:00"))
    commitment_store = InboxIntelligenceStore(tmp_path / "commitments.db")
    client = _FakeClient(["HAS_COMMITMENT: yes\nDESCRIPTION: Alice will investigate the issue\nDEADLINE_PHRASE: NONE"])

    scan_for_commitments(gmail_store, commitment_store, _ACCOUNT_EMAIL, client, "claude-haiku-4-5", _FakeAnalyzer())

    open_commitments = commitment_store.list_open_commitments()
    assert open_commitments[0]["deadline_phrase"] is None
    assert open_commitments[0]["due_date"] is None


def test_unresolvable_deadline_phrase_stores_commitment_with_no_due_date(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-12T00:00:00+00:00"))
    commitment_store = InboxIntelligenceStore(tmp_path / "commitments.db")
    client = _FakeClient(["HAS_COMMITMENT: yes\nDESCRIPTION: Alice will follow up\nDEADLINE_PHRASE: sometime next quarter"])

    scan_for_commitments(gmail_store, commitment_store, _ACCOUNT_EMAIL, client, "claude-haiku-4-5", _FakeAnalyzer())

    open_commitments = commitment_store.list_open_commitments()
    assert open_commitments[0]["description"] == "Alice will follow up"
    assert open_commitments[0]["due_date"] is None


def test_redacts_before_sending_and_untokenizes_the_response(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(
        _message(
            "m1", "t1", "Alice <alice@example.com>", "2024-06-12T00:00:00+00:00",
            body_text="Jane Doe will send it by Friday",
        )
    )
    commitment_store = InboxIntelligenceStore(tmp_path / "commitments.db")
    client = _FakeClient(["HAS_COMMITMENT: yes\nDESCRIPTION: Jane Doe will send the report\nDEADLINE_PHRASE: by Friday"])

    scan_for_commitments(
        gmail_store, commitment_store, _ACCOUNT_EMAIL, client, "claude-haiku-4-5", _FakeAnalyzer(needle="Jane Doe")
    )

    sent_user_message = client.messages.calls[0]["messages"][0]["content"]
    assert "Jane Doe" not in sent_user_message
    assert "<PERSON_1>" in sent_user_message
    # the response, which echoed the placeholder back, is untokenized before storing
    assert commitment_store.list_open_commitments()[0]["description"] == "Jane Doe will send the report"


def test_audit_event_recorded_for_each_llm_call(tmp_path):
    gmail_store = GmailStore(tmp_path / "gmail.db")
    gmail_store.upsert_message(_message("m1", "t1", "Alice <alice@example.com>", "2024-06-12T00:00:00+00:00"))
    commitment_store = InboxIntelligenceStore(tmp_path / "commitments.db")
    client = _FakeClient([_NO_COMMITMENT])
    audit_log_dir = tmp_path / "logs"

    scan_for_commitments(
        gmail_store, commitment_store, _ACCOUNT_EMAIL, client, "claude-haiku-4-5", _FakeAnalyzer(),
        audit_log_dir=audit_log_dir,
    )

    lines = (audit_log_dir / "audit.log").read_text().strip().splitlines()
    assert len(lines) == 1
