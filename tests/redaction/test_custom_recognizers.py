from meridian.redaction.custom_recognizers import find_secret_spans


def test_finds_openai_style_key():
    text = "here is my key: sk-abcdefghijklmnopqrstuvwxyz123456"
    spans = find_secret_spans(text)

    assert len(spans) == 1
    assert spans[0].entity_type == "API_KEY_OR_PASSWORD"
    matched = text[spans[0].start : spans[0].end]
    assert matched.startswith("sk-")


def test_finds_github_style_token():
    text = "token=ghp_abcdefghijklmnopqrstuvwxyz123456"
    spans = find_secret_spans(text)

    assert any(text[s.start : s.end].startswith("ghp_") for s in spans)


def test_finds_aws_access_key():
    text = "AWS key: AKIAABCDEFGHIJKLMNOP"
    spans = find_secret_spans(text)

    assert any(text[s.start : s.end] == "AKIAABCDEFGHIJKLMNOP" for s in spans)


def test_finds_password_assignment():
    text = "password: hunter2isnotreal"
    spans = find_secret_spans(text)

    assert len(spans) == 1


def test_ignores_ordinary_text():
    text = "let's meet for coffee tomorrow at the usual place"
    spans = find_secret_spans(text)

    assert spans == []
