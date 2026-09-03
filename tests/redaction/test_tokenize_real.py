import pytest

from meridian.redaction.tokenize import tokenize_for_external_call, untokenize

try:
    from meridian.redaction.analyzer import build_analyzer_engine

    _analyzer = build_analyzer_engine()
except Exception as exc:  # pragma: no cover - depends on local model install
    _analyzer = None
    _skip_reason = f"presidio analyzer/spacy model not available: {exc}"


@pytest.fixture(scope="module")
def analyzer():
    if _analyzer is None:
        pytest.skip(_skip_reason)
    return _analyzer


def test_real_pipeline_tokenizes_person_email_and_phone(analyzer):
    text = "Contact John Smith at john@example.com or 555-123-4567"

    result = tokenize_for_external_call(text, analyzer=analyzer)

    assert "John Smith" not in result.tokenized_text
    assert "john@example.com" not in result.tokenized_text
    assert "555-123-4567" not in result.tokenized_text
    assert any(k.startswith("<PERSON_") for k in result.mapping)
    assert any(k.startswith("<EMAIL_ADDRESS_") for k in result.mapping)
    assert any(k.startswith("<PHONE_NUMBER_") for k in result.mapping)
    assert untokenize(result.tokenized_text, result.mapping) == text


def test_real_pipeline_leaves_excluded_entities_untouched(analyzer):
    text = "Meeting in Boston on Jan 5 at https://example.com"

    result = tokenize_for_external_call(text, analyzer=analyzer)

    assert "Boston" in result.tokenized_text
    assert "Jan 5" in result.tokenized_text
    assert "https://example.com" in result.tokenized_text


def test_real_pipeline_redacts_credit_card_permanently(analyzer):
    text = "My card number is 4111111111111111 for the order"

    result = tokenize_for_external_call(text, analyzer=analyzer)

    assert "4111111111111111" not in result.tokenized_text
    assert "[REDACTED]" in result.tokenized_text
    assert result.mapping == {}
