from meridian.ingestion.docs.doc_parser import _flatten_content


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
