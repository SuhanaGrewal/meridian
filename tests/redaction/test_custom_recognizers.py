from meridian.redaction.custom_recognizers import find_address_spans, find_secret_spans


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


def test_finds_simple_street_address():
    text = "please ship it to 123 Main St"
    spans = find_address_spans(text)

    assert len(spans) == 1
    assert spans[0].entity_type == "HOME_ADDRESS"
    assert text[spans[0].start : spans[0].end] == "123 Main St"


def test_finds_address_with_city_state_zip():
    text = "my address is 456 Oak Avenue, Springfield, IL 62704 if you need it"
    spans = find_address_spans(text)

    assert len(spans) == 1
    matched = text[spans[0].start : spans[0].end]
    assert matched.startswith("456 Oak Avenue")
    assert matched.endswith("62704")


def test_finds_address_with_apartment():
    text = "789 N Elm Blvd Apt 4B is where I live"
    spans = find_address_spans(text)

    assert len(spans) == 1
    assert "Apt 4B" in text[spans[0].start : spans[0].end]


def test_ignores_text_without_address():
    text = "let's meet for coffee tomorrow at the usual place"
    spans = find_address_spans(text)

    assert spans == []
