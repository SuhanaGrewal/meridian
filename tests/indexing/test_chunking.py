from meridian.indexing.chunking import split_into_paragraphs, split_into_sentences


def test_split_into_paragraphs_on_blank_lines():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."

    assert split_into_paragraphs(text) == [
        "First paragraph.",
        "Second paragraph.",
        "Third paragraph.",
    ]


def test_split_into_paragraphs_collapses_multiple_blank_lines():
    text = "First.\n\n\n\nSecond."

    assert split_into_paragraphs(text) == ["First.", "Second."]


def test_split_into_paragraphs_drops_empty_results():
    text = "\n\nFirst.\n\n\n\nSecond.\n\n"

    assert split_into_paragraphs(text) == ["First.", "Second."]


def test_split_into_paragraphs_single_paragraph():
    assert split_into_paragraphs("Just one paragraph here.") == ["Just one paragraph here."]


def test_split_into_sentences_basic():
    text = "This is one sentence. This is another one. And a third."

    assert split_into_sentences(text) == [
        "This is one sentence.",
        "This is another one.",
        "And a third.",
    ]


def test_split_into_sentences_handles_question_and_exclamation():
    text = "Is this a question? Yes it is! Great."

    assert split_into_sentences(text) == ["Is this a question?", "Yes it is!", "Great."]


def test_split_into_sentences_does_not_split_on_abbreviation_style_period_before_lowercase():
    text = "Dr. smith arrived. He was late."

    result = split_into_sentences(text)

    # a period followed by a lowercase letter is not treated as a sentence
    # boundary (the regex requires an uppercase letter or digit after the
    # whitespace) - "Dr. smith" stays together, imperfect but low-risk.
    assert result == ["Dr. smith arrived.", "He was late."]


def test_split_into_sentences_single_sentence():
    assert split_into_sentences("Just one sentence.") == ["Just one sentence."]
