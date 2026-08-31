import pytest

from meridian.ingestion.docs.doc_parser import (
    DocParseError,
    _flatten_content,
    _flatten_table,
    parse_document,
)


def _text_paragraph(text: str, *, style: str | None = None, bullet: bool = False) -> dict:
    paragraph: dict = {"elements": [{"textRun": {"content": text}}]}
    if style:
        paragraph["paragraphStyle"] = {"namedStyleType": style}
    if bullet:
        paragraph["bullet"] = {"listId": "list-1"}
    return {"paragraph": paragraph}


def test_flatten_content_plain_paragraph():
    body = [_text_paragraph("Hello world\n")]

    assert _flatten_content(body) == "Hello world"


def test_flatten_content_multiple_paragraphs():
    body = [_text_paragraph("First\n"), _text_paragraph("Second\n")]

    assert _flatten_content(body) == "First\nSecond"


def test_flatten_content_heading_gets_markdown_prefix():
    body = [_text_paragraph("My Heading\n", style="HEADING_1")]

    assert _flatten_content(body) == "# My Heading"


def test_flatten_content_subtitle_and_title_prefixes():
    assert _flatten_content([_text_paragraph("Doc Title\n", style="TITLE")]) == "# Doc Title"
    assert _flatten_content([_text_paragraph("A Subtitle\n", style="SUBTITLE")]) == "## A Subtitle"


def test_flatten_content_bullet_item_gets_dash_prefix():
    body = [_text_paragraph("An item\n", bullet=True)]

    assert _flatten_content(body) == "- An item"


def test_flatten_content_skips_empty_paragraphs():
    body = [_text_paragraph("\n"), _text_paragraph("Real content\n")]

    assert _flatten_content(body) == "Real content"


def test_flatten_content_empty_body_returns_empty_string():
    assert _flatten_content([]) == ""


def _cell(text: str) -> dict:
    return {"content": [_text_paragraph(text)]}


def test_flatten_table_joins_cells_and_rows():
    table = {
        "tableRows": [
            {"tableCells": [_cell("A1\n"), _cell("B1\n")]},
            {"tableCells": [_cell("A2\n"), _cell("B2\n")]},
        ]
    }

    assert _flatten_table(table) == "A1 | B1\nA2 | B2"


def test_flatten_table_empty_returns_empty_string():
    assert _flatten_table({"tableRows": []}) == ""


def test_flatten_content_includes_table_between_paragraphs():
    body = [
        _text_paragraph("Before\n"),
        {"table": {"tableRows": [{"tableCells": [_cell("X\n")]}]}},
        _text_paragraph("After\n"),
    ]

    assert _flatten_content(body) == "Before\nX\nAfter"


def test_parse_document_extracts_title_and_content():
    raw = {
        "documentId": "doc-1",
        "title": "My Doc",
        "body": {"content": [_text_paragraph("Hello\n")]},
    }

    parsed = parse_document(raw, modified_time="2024-06-01T00:00:00.000Z")

    assert parsed.doc_id == "doc-1"
    assert parsed.title == "My Doc"
    assert parsed.content_text == "Hello"
    assert parsed.modified_time == "2024-06-01T00:00:00.000Z"
    assert len(parsed.content_hash) == 64


def test_parse_document_missing_document_id_raises():
    with pytest.raises(DocParseError):
        parse_document({"title": "no id"}, modified_time=None)


def test_parse_document_tolerates_missing_body():
    parsed = parse_document({"documentId": "doc-2"}, modified_time=None)

    assert parsed.title == ""
    assert parsed.content_text == ""


def test_parse_document_hash_changes_when_content_changes():
    raw_one = {"documentId": "doc-3", "title": "T", "body": {"content": [_text_paragraph("A\n")]}}
    raw_two = {"documentId": "doc-3", "title": "T", "body": {"content": [_text_paragraph("B\n")]}}

    hash_one = parse_document(raw_one, modified_time=None).content_hash
    hash_two = parse_document(raw_two, modified_time=None).content_hash

    assert hash_one != hash_two
