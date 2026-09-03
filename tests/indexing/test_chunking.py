from meridian.indexing.chunking import (
    _atomize,
    _split_oversized,
    pack_into_windows,
    split_into_paragraphs,
    split_into_sections,
    split_into_sentences,
)


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


def test_split_into_sections_splits_on_headings():
    text = "# Title\nIntro text.\n\n## Subsection\nMore text here."

    sections = split_into_sections(text)

    assert len(sections) == 2
    assert sections[0].startswith("# Title")
    assert sections[1].startswith("## Subsection")


def test_split_into_sections_keeps_leading_content_before_first_heading():
    text = "Some intro with no heading.\n\n# First Heading\nBody text."

    sections = split_into_sections(text)

    assert sections[0] == "Some intro with no heading."
    assert sections[1].startswith("# First Heading")


def test_split_into_sections_no_headings_returns_single_section():
    text = "Just plain text.\n\nNo headings anywhere in here."

    assert split_into_sections(text) == [text]


def test_split_into_sections_empty_text_returns_empty_list():
    assert split_into_sections("") == []
    assert split_into_sections("   \n\n  ") == []


def test_split_into_sections_heading_at_end_with_no_body():
    text = "Intro.\n\n# Trailing Heading"

    sections = split_into_sections(text)

    assert sections == ["Intro.", "# Trailing Heading"]


def test_split_oversized_fixed_size_fallback():
    atom = "x" * 25

    pieces = _split_oversized(atom, 10)

    assert pieces == ["x" * 10, "x" * 10, "x" * 5]


def test_atomize_keeps_short_paragraphs_whole():
    text = "Short one.\n\nShort two."

    assert _atomize(text, 100) == ["Short one.", "Short two."]


def test_atomize_splits_oversized_paragraph_into_sentences():
    text = "This is sentence one. This is sentence two. This is sentence three."

    atoms = _atomize(text, 30)

    assert atoms == [
        "This is sentence one.",
        "This is sentence two.",
        "This is sentence three.",
    ]


def test_atomize_falls_back_to_fixed_split_for_oversized_sentence():
    text = "x" * 50  # one giant "sentence" with no punctuation at all

    atoms = _atomize(text, 20)

    assert atoms == ["x" * 20, "x" * 20, "x" * 10]


def test_pack_into_windows_fits_in_one_window_when_short():
    text = "Short paragraph one.\n\nShort paragraph two."

    windows = pack_into_windows(text, target_size=1000)

    assert windows == ["Short paragraph one. Short paragraph two."]


def test_pack_into_windows_splits_into_multiple_when_long():
    paragraphs = [f"Paragraph number {i} with some filler words in it." for i in range(10)]
    text = "\n\n".join(paragraphs)

    windows = pack_into_windows(text, target_size=100)

    assert len(windows) > 1
    for window in windows:
        assert len(window) <= 100 + 1  # +1 for a joining space, no overlap here


def test_pack_into_windows_carries_overlap_into_next_window():
    paragraphs = [f"Paragraph {i} has some words padding it out further." for i in range(6)]
    text = "\n\n".join(paragraphs)

    windows = pack_into_windows(text, target_size=80, overlap=20)

    assert len(windows) > 1
    tail_of_first = windows[0][-20:].strip()
    assert tail_of_first in windows[1]


def test_pack_into_windows_zero_overlap_means_no_carry():
    paragraphs = [f"Paragraph {i} has some words padding it out further." for i in range(6)]
    text = "\n\n".join(paragraphs)

    windows = pack_into_windows(text, target_size=80, overlap=0)

    # each window should start with the same text as a fresh atom, not a
    # fragment of the previous window's tail
    assert windows[1].startswith("Paragraph")


def test_pack_into_windows_empty_text_returns_empty_list():
    assert pack_into_windows("", target_size=100) == []
    assert pack_into_windows("   ", target_size=100) == []
