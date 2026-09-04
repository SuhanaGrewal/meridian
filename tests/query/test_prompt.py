from meridian.query.prompt import SYSTEM_PROMPT, _source_label
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
