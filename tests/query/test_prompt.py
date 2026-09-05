from datetime import datetime, timezone

from meridian.query.prompt import SYSTEM_PROMPT, _relative_days_label, _source_label, build_user_message, format_sources
from meridian.query.retrieval import RetrievedChunk


def _chunk(source, metadata, source_item_id="item-1"):
    return RetrievedChunk(
        chunk_id=f"{source}:{source_item_id}:0000",
        source=source,
        source_item_id=source_item_id,
        parent_text="some text",
        metadata=metadata,
        confidence=0.9,
    )


def test_system_prompt_mentions_citations():
    assert "cite" in SYSTEM_PROMPT.lower()


def test_system_prompt_mentions_placeholders():
    assert "<PERSON_1>" in SYSTEM_PROMPT


def test_system_prompt_has_no_user_data():
    # a sanity check that this stays a fixed constant with no interpolation
    assert "{" not in SYSTEM_PROMPT


def test_system_prompt_mentions_recency_reasoning():
    assert "today" in SYSTEM_PROMPT.lower()
    assert "upcoming" in SYSTEM_PROMPT.lower()


def test_relative_days_label_past():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)

    assert _relative_days_label("2026-05-14T00:00:00+00:00", now) == " (114 days ago)"


def test_relative_days_label_future():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)

    assert _relative_days_label("2026-09-08T00:00:00+00:00", now) == " (in 3 days)"


def test_relative_days_label_today():
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)

    assert _relative_days_label("2026-09-05T00:00:00+00:00", now) == " (today)"


def test_relative_days_label_singular_day():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)

    assert _relative_days_label("2026-09-04T00:00:00+00:00", now) == " (1 day ago)"
    assert _relative_days_label("2026-09-06T00:00:00+00:00", now) == " (in 1 day)"


def test_relative_days_label_missing_or_unparseable_date_returns_empty():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)

    assert _relative_days_label("", now) == ""
    assert _relative_days_label("not a date", now) == ""


def test_source_label_gmail_includes_relative_days_ago():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    label = _source_label(
        _chunk("gmail", {"sender": "alice@example.com", "sent_at": "2026-05-14T00:00:00+00:00", "subject": "Hi"}),
        now=now,
    )

    assert "114 days ago" in label


def test_source_label_calendar_includes_relative_days_future():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    label = _source_label(
        _chunk("calendar", {"summary": "Standup", "start_at": "2026-09-08T00:00:00+00:00"}), now=now
    )

    assert "in 3 days" in label


def test_source_label_gmail():
    label = _source_label(_chunk("gmail", {"sender": "alice@example.com", "sent_at": "2024-06-01", "subject": "Hi"}))

    assert "alice@example.com" in label
    assert "2024-06-01" in label
    assert "Hi" in label


def test_source_label_calendar():
    label = _source_label(_chunk("calendar", {"summary": "Standup", "start_at": "2024-06-01T10:00:00Z"}))

    assert "Standup" in label
    assert "2024-06-01T10:00:00Z" in label


def test_source_label_docs():
    label = _source_label(_chunk("docs", {"title": "Project Roadmap"}))

    assert "Project Roadmap" in label


def test_source_label_local_files():
    label = _source_label(_chunk("local_files", {"path": "notes/meeting.txt"}))

    assert "notes/meeting.txt" in label


def test_source_label_handles_missing_metadata_gracefully():
    label = _source_label(_chunk("gmail", {}))

    assert "Gmail" in label


def _chunk_with_text(source, metadata, parent_text, source_item_id="item-1"):
    return RetrievedChunk(
        chunk_id=f"{source}:{source_item_id}:0000",
        source=source,
        source_item_id=source_item_id,
        parent_text=parent_text,
        metadata=metadata,
        confidence=0.9,
    )


def test_build_user_message_includes_question_and_numbered_context():
    chunks = [
        _chunk_with_text("gmail", {"subject": "Budget"}, "Budget details here", source_item_id="msg-1"),
        _chunk_with_text("docs", {"title": "Roadmap"}, "Roadmap details here", source_item_id="doc-1"),
    ]

    message = build_user_message("What's the budget?", chunks)

    assert "Question:\nWhat's the budget?" in message
    assert "[1]" in message
    assert "Budget details here" in message
    assert "[2]" in message
    assert "Roadmap details here" in message


def test_build_user_message_with_no_chunks():
    message = build_user_message("A question with no context", [])

    assert "Question:\nA question with no context" in message
    assert "Context:" in message


def test_build_user_message_includes_todays_date():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)

    message = build_user_message("What flights do I have?", [], now=now)

    assert "Today's date: 2026-09-05" in message
    assert message.index("Today's date") < message.index("Question:")


def test_build_user_message_defaults_now_when_not_given():
    message = build_user_message("A question", [])

    assert "Today's date:" in message


def test_build_user_message_with_history_prepends_conversation():
    history = [
        {"role": "user", "content": "what's on my calendar this month"},
        {"role": "assistant", "content": "You have a meeting on the 10th [1]."},
    ]

    message = build_user_message("what about next month", [], history=history)

    assert "Recent conversation in this thread:" in message
    assert "User: what's on my calendar this month" in message
    assert "Assistant: You have a meeting on the 10th [1]." in message
    assert message.index("Recent conversation") < message.index("Question:")


def test_build_user_message_without_history_omits_conversation_section():
    message = build_user_message("a question", [])

    assert "Recent conversation" not in message


def test_format_sources_numbers_match_build_user_message():
    chunks = [_chunk("gmail", {"subject": "Budget"}), _chunk("docs", {"title": "Roadmap"})]

    sources = format_sources(chunks)

    assert "[1]" in sources
    assert "[2]" in sources
    assert "Budget" in sources
    assert "Roadmap" in sources


def test_format_sources_empty_chunks():
    assert format_sources([]) == "Sources:"
