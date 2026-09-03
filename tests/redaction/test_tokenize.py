from meridian.redaction.custom_recognizers import Span
from meridian.redaction.tokenize import (
    TokenizationResult,
    _merge_spans,
    _spans_overlap,
    tokenize_for_external_call,
)


class _FakeAnalyzer:
    def __init__(self, results):
        self._results = results

    def analyze(self, *, text, entities, language):
        return self._results


def test_tokenization_result_holds_fields():
    result = TokenizationResult(
        tokenized_text="hi <PERSON_1>",
        mapping={"<PERSON_1>": "John"},
        entity_counts={"PERSON": 1},
    )

    assert result.tokenized_text == "hi <PERSON_1>"
    assert result.mapping == {"<PERSON_1>": "John"}
    assert result.entity_counts == {"PERSON": 1}


def test_spans_overlap_true_for_overlapping_ranges():
    a = Span(entity_type="A", start=0, end=10)
    b = Span(entity_type="B", start=5, end=15)

    assert _spans_overlap(a, b) is True


def test_spans_overlap_false_for_disjoint_ranges():
    a = Span(entity_type="A", start=0, end=5)
    b = Span(entity_type="B", start=5, end=10)

    assert _spans_overlap(a, b) is False


def test_merge_spans_includes_non_overlapping_custom_spans():
    presidio_spans = [Span(entity_type="PERSON", start=0, end=4)]
    custom_spans = [Span(entity_type="HOME_ADDRESS", start=10, end=20)]

    merged = _merge_spans(presidio_spans, custom_spans)

    assert len(merged) == 2


def test_merge_spans_drops_overlapping_custom_spans():
    presidio_spans = [Span(entity_type="PERSON", start=0, end=10)]
    custom_spans = [Span(entity_type="HOME_ADDRESS", start=5, end=15)]

    merged = _merge_spans(presidio_spans, custom_spans)

    assert merged == presidio_spans


def test_tokenize_reversible_entity_gets_numbered_placeholder():
    text = "Hi John, nice to meet you"
    analyzer = _FakeAnalyzer([Span(entity_type="PERSON", start=3, end=7)])

    result = tokenize_for_external_call(text, analyzer=analyzer)

    assert result.tokenized_text == "Hi <PERSON_1>, nice to meet you"
    assert result.mapping == {"<PERSON_1>": "John"}
    assert result.entity_counts == {"PERSON": 1}


def test_tokenize_numbers_multiple_same_type_entities_left_to_right():
    text = "John met Mary"
    analyzer = _FakeAnalyzer(
        [
            Span(entity_type="PERSON", start=0, end=4),
            Span(entity_type="PERSON", start=9, end=13),
        ]
    )

    result = tokenize_for_external_call(text, analyzer=analyzer)

    assert result.tokenized_text == "<PERSON_1> met <PERSON_2>"
    assert result.mapping == {"<PERSON_1>": "John", "<PERSON_2>": "Mary"}
    assert result.entity_counts == {"PERSON": 2}


def test_tokenize_hard_secret_becomes_redacted_marker_not_in_mapping():
    text = "card: 4111111111111111"
    analyzer = _FakeAnalyzer([Span(entity_type="CREDIT_CARD", start=6, end=22)])

    result = tokenize_for_external_call(text, analyzer=analyzer)

    assert result.tokenized_text == "card: [REDACTED]"
    assert result.mapping == {}
    assert result.entity_counts == {"CREDIT_CARD": 1}


def test_tokenize_empty_text_returns_empty_result_without_calling_analyzer():
    class _ExplodingAnalyzer:
        def analyze(self, **kwargs):
            raise AssertionError("should not be called for empty text")

    result = tokenize_for_external_call("", analyzer=_ExplodingAnalyzer())

    assert result == TokenizationResult(tokenized_text="", mapping={}, entity_counts={})


def test_tokenize_includes_custom_address_and_secret_spans():
    text = "ship to 123 Main St, key: sk-abcdefghijklmnopqrstuvwxyz123456"
    analyzer = _FakeAnalyzer([])

    result = tokenize_for_external_call(text, analyzer=analyzer)

    assert "<HOME_ADDRESS_1>" in result.tokenized_text
    assert "[REDACTED]" in result.tokenized_text
    assert result.mapping == {"<HOME_ADDRESS_1>": "123 Main St"}
    assert result.entity_counts == {"HOME_ADDRESS": 1, "API_KEY_OR_PASSWORD": 1}


def test_tokenize_logs_entity_counts_without_raw_values():
    logged = {}

    class _RecordingLogger:
        def info(self, message, extra=None):
            logged["extra"] = extra

    text = "Hi John"
    analyzer = _FakeAnalyzer([Span(entity_type="PERSON", start=3, end=7)])

    tokenize_for_external_call(text, analyzer=analyzer, logger=_RecordingLogger())

    assert logged["extra"]["entity_counts"] == {"PERSON": 1}
    assert "John" not in str(logged["extra"])
