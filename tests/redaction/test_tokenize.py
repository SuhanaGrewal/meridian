from meridian.redaction.custom_recognizers import Span
from meridian.redaction.tokenize import TokenizationResult, _merge_spans, _spans_overlap


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
