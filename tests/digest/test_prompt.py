from meridian.digest.prompt import (
    SYSTEM_PROMPT,
    build_digest_message,
    build_plaintext_digest,
    format_sources,
)

_PII_PARAGRAPH = (
    "Some names, email addresses, phone numbers, and addresses in the items "
    "have been replaced with placeholders like <PERSON_1>, <EMAIL_ADDRESS_1>, "
    "<PHONE_NUMBER_1>, or <HOME_ADDRESS_1> to protect privacy. Treat these "
    "exactly like real names/emails/etc. in your answer - use them naturally in "
    "place of the real values, and do not comment on or explain the "
    "placeholders themselves."
)


def _item(source="gmail", label="Gmail email from a@example.com", detail="hello") -> dict:
    return {"source": source, "label": label, "detail": detail}


def test_system_prompt_contains_pii_placeholder_paragraph_verbatim():
    assert _PII_PARAGRAPH in SYSTEM_PROMPT


def test_build_digest_message_numbers_items_in_order():
    items = [_item(label="first"), _item(label="second")]

    message = build_digest_message("2024-06-01T00:00:00Z", "2024-06-02T00:00:00Z", items)

    assert "Digest window: 2024-06-01T00:00:00Z to 2024-06-02T00:00:00Z" in message
    assert "[1] first" in message
    assert "[2] second" in message
    assert message.index("[1] first") < message.index("[2] second")


def test_build_digest_message_omits_empty_detail():
    items = [_item(label="entity mention", detail="")]

    message = build_digest_message("s", "e", items)

    lines = message.splitlines()
    assert lines[-1] == "[1] entity mention"


def test_build_digest_message_empty_items():
    message = build_digest_message("s", "e", [])

    assert "Items:" in message


def test_format_sources_numbers_items_in_order():
    items = [_item(label="first"), _item(label="second")]

    sources = format_sources(items)

    assert sources == "Sources:\n[1] first\n[2] second"


def test_build_plaintext_digest_empty_items():
    assert build_plaintext_digest([]) == "Nothing new."


def test_build_plaintext_digest_groups_by_source_in_fixed_order():
    items = [
        _item(source="docs", label="doc item"),
        _item(source="gmail", label="gmail item"),
        _item(source="calendar", label="calendar item"),
    ]

    text = build_plaintext_digest(items)

    assert text.index("gmail:") < text.index("calendar:") < text.index("docs:")
    assert "- gmail item" in text
    assert "- calendar item" in text
    assert "- doc item" in text


def test_build_plaintext_digest_skips_sources_with_no_items():
    items = [_item(source="gmail", label="gmail item")]

    text = build_plaintext_digest(items)

    assert "calendar:" not in text
    assert "docs:" not in text
