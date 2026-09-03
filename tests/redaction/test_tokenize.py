from dataclasses import dataclass

from meridian.redaction.custom_recognizers import Span
from meridian.redaction.tokenize import (
    TokenizationResult,
    _resolve_overlaps,
    _spans_overlap,
    tokenize_for_external_call,
    untokenize,
)


class _FakeAnalyzer:
    def __init__(self, results):
        self._results = results

    def analyze(self, *, text, entities, language):
        return self._results


@dataclass(frozen=True)
class _ScoredSpan:
    """mimics a real presidio RecognizerResult, which (unlike our own Span
    dataclass) always carries a confidence score."""

    entity_type: str
    start: int
    end: int
    score: float


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


def test_resolve_overlaps_keeps_non_overlapping_spans():
    presidio_span = _ScoredSpan(entity_type="PERSON", start=0, end=4, score=0.9)
    custom_span = Span(entity_type="HOME_ADDRESS", start=10, end=20)

    resolved = _resolve_overlaps([presidio_span, custom_span])

    assert set(resolved) == {presidio_span, custom_span}


def test_resolve_overlaps_drops_overlapping_custom_span_in_favor_of_presidio():
    presidio_span = _ScoredSpan(entity_type="PERSON", start=0, end=10, score=0.9)
    custom_span = Span(entity_type="HOME_ADDRESS", start=5, end=15)

    resolved = _resolve_overlaps([presidio_span, custom_span])

    assert resolved == [presidio_span]


def test_resolve_overlaps_keeps_highest_scoring_presidio_span():
    # reproduces a real observed case: a credit card number also weakly
    # matched us_bank_number and us_driver_license patterns, all overlapping
    strong = _ScoredSpan(entity_type="CREDIT_CARD", start=10, end=26, score=1.0)
    weak_1 = _ScoredSpan(entity_type="US_BANK_NUMBER", start=10, end=26, score=0.05)
    weak_2 = _ScoredSpan(entity_type="US_DRIVER_LICENSE", start=10, end=26, score=0.01)

    resolved = _resolve_overlaps([weak_1, weak_2, strong])

    assert resolved == [strong]


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


def test_tokenize_does_not_corrupt_text_when_presidio_spans_overlap():
    # regression test: presidio can return multiple overlapping matches for
    # the same substring (e.g. a credit card number also weakly matching
    # us_bank_number/us_driver_license) - processing all of them used to
    # slice the string using stale offsets and silently drop trailing text.
    text = "my card is 4111111111111111 done"
    analyzer = _FakeAnalyzer(
        [
            _ScoredSpan(entity_type="CREDIT_CARD", start=11, end=27, score=1.0),
            _ScoredSpan(entity_type="US_BANK_NUMBER", start=11, end=27, score=0.05),
            _ScoredSpan(entity_type="US_DRIVER_LICENSE", start=11, end=27, score=0.01),
        ]
    )

    result = tokenize_for_external_call(text, analyzer=analyzer)

    assert result.tokenized_text == "my card is [REDACTED] done"
    assert result.entity_counts == {"CREDIT_CARD": 1}


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


def test_untokenize_restores_reversible_values():
    tokenized = "Hi <PERSON_1>, nice to meet you"

    restored = untokenize(tokenized, {"<PERSON_1>": "John"})

    assert restored == "Hi John, nice to meet you"


def test_untokenize_round_trips_with_tokenize_for_reversible_only_text():
    text = "John met Mary at the office"
    analyzer = _FakeAnalyzer(
        [
            Span(entity_type="PERSON", start=0, end=4),
            Span(entity_type="PERSON", start=9, end=13),
        ]
    )

    result = tokenize_for_external_call(text, analyzer=analyzer)
    restored = untokenize(result.tokenized_text, result.mapping)

    assert restored == text


def test_untokenize_cannot_restore_a_hard_secret():
    text = "card: 4111111111111111"
    analyzer = _FakeAnalyzer([Span(entity_type="CREDIT_CARD", start=6, end=22)])

    result = tokenize_for_external_call(text, analyzer=analyzer)
    restored = untokenize(result.tokenized_text, result.mapping)

    assert restored == "card: [REDACTED]"
    assert "4111111111111111" not in restored


def test_untokenize_with_empty_mapping_returns_text_unchanged():
    assert untokenize("no placeholders here", {}) == "no placeholders here"
