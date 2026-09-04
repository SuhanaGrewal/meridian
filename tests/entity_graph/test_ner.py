from meridian.entity_graph.ner import ExtractedEntity, extract_entities


class _FakeSpan:
    def __init__(self, text, label, start_char, end_char):
        self.text = text
        self.label_ = label
        self.start_char = start_char
        self.end_char = end_char


class _FakeDoc:
    def __init__(self, ents):
        self.ents = ents


class _FakeNlp:
    def __init__(self, ents):
        self._ents = ents
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)
        return _FakeDoc(self._ents)


def test_extract_entities_returns_matching_types():
    nlp = _FakeNlp(
        [
            _FakeSpan("Jane Doe", "PERSON", 0, 8),
            _FakeSpan("Acme Corp", "ORG", 12, 21),
        ]
    )

    result = extract_entities(nlp, "Jane Doe works at Acme Corp")

    assert result == [
        ExtractedEntity(text="Jane Doe", label="PERSON", start_char=0, end_char=8),
        ExtractedEntity(text="Acme Corp", label="ORG", start_char=12, end_char=21),
    ]


def test_extract_entities_filters_out_unwanted_types():
    nlp = _FakeNlp(
        [
            _FakeSpan("Jane Doe", "PERSON", 0, 8),
            _FakeSpan("Monday", "DATE", 20, 26),
            _FakeSpan("French", "NORP", 30, 36),
        ]
    )

    result = extract_entities(nlp, "some text")

    assert len(result) == 1
    assert result[0].label == "PERSON"


def test_extract_entities_respects_custom_entity_types():
    nlp = _FakeNlp([_FakeSpan("Monday", "DATE", 0, 6)])

    result = extract_entities(nlp, "some text", entity_types={"DATE"})

    assert len(result) == 1
    assert result[0].label == "DATE"


def test_extract_entities_empty_text_returns_empty_without_calling_nlp():
    nlp = _FakeNlp([_FakeSpan("Jane Doe", "PERSON", 0, 8)])

    result = extract_entities(nlp, "   ")

    assert result == []
    assert nlp.calls == []


def test_extract_entities_no_entities_found():
    nlp = _FakeNlp([])

    result = extract_entities(nlp, "some text with nothing notable")

    assert result == []
