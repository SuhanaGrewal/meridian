from meridian.indexing.chunking import PARENT_CHUNK_CHARS
from meridian.indexing.parent_child import build_chunks


def test_short_text_is_its_own_parent():
    text = "Just a short email body."

    records = build_chunks(text)

    assert len(records) == 1
    assert records[0].text == text
    assert records[0].parent_text == text
    assert records[0].position == 0
    assert records[0].is_own_parent is True


def test_empty_text_returns_no_records():
    assert build_chunks("") == []
    assert build_chunks("   ") == []


def test_long_text_without_headings_produces_multiple_children_with_shared_parents():
    paragraphs = [f"Paragraph {i}. " + ("filler word " * 20) for i in range(20)]
    text = "\n\n".join(paragraphs)
    assert len(text) > PARENT_CHUNK_CHARS

    records = build_chunks(text, has_headings=False)

    assert len(records) > 1
    assert all(not r.is_own_parent for r in records)
    # positions are sequential starting at 0
    assert [r.position for r in records] == list(range(len(records)))
    # multiple children should share the same parent_text (grouped together)
    parent_texts = {r.parent_text for r in records}
    assert len(parent_texts) < len(records)


def test_long_text_with_headings_keeps_sections_separate():
    section_a = "# Section A\n" + ("Alpha content sentence. " * 60)
    section_b = "# Section B\n" + ("Beta content sentence. " * 60)
    text = section_a + "\n\n" + section_b
    assert len(text) > PARENT_CHUNK_CHARS

    records = build_chunks(text, has_headings=True)

    a_parents = {r.parent_text for r in records if "Alpha" in r.parent_text}
    b_parents = {r.parent_text for r in records if "Beta" in r.parent_text}

    # no parent window should mix content from both sections
    assert not any("Beta" in p for p in a_parents)
    assert not any("Alpha" in p for p in b_parents)


def test_child_chunks_are_substrings_of_reasonable_content():
    paragraphs = [f"Paragraph {i}. " + ("filler word " * 20) for i in range(20)]
    text = "\n\n".join(paragraphs)

    records = build_chunks(text)

    for record in records:
        assert record.text
        assert record.parent_text
        assert len(record.text) <= len(record.parent_text) + 1
