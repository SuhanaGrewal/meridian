from meridian.query.prompt import SYSTEM_PROMPT, _source_label, build_user_message, format_sources
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


def test_format_sources_numbers_match_build_user_message():
    chunks = [_chunk("gmail", {"subject": "Budget"}), _chunk("docs", {"title": "Roadmap"})]

    sources = format_sources(chunks)

    assert "[1]" in sources
    assert "[2]" in sources
    assert "Budget" in sources
    assert "Roadmap" in sources


def test_format_sources_empty_chunks():
    assert format_sources([]) == "Sources:"
