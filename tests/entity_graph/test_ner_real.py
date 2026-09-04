import pytest

from meridian.entity_graph.ner import extract_entities

try:
    from meridian.entity_graph.ner import build_ner_engine

    _nlp = build_ner_engine()
except Exception as exc:  # pragma: no cover - depends on model download/network
    _nlp = None
    _skip_reason = f"en_core_web_lg model not available: {exc}"


@pytest.fixture(scope="module")
def nlp():
    if _nlp is None:
        pytest.skip(_skip_reason)
    return _nlp


def test_real_ner_extracts_person_org_and_location(nlp):
    text = "Jane Doe met with the Acme Corp team in Paris on Monday."

    result = extract_entities(nlp, text)
    labels_and_texts = {(entity.label, entity.text) for entity in result}

    assert ("PERSON", "Jane Doe") in labels_and_texts
    assert ("ORG", "Acme Corp") in labels_and_texts
    assert ("GPE", "Paris") in labels_and_texts
    # Monday is a DATE, excluded by the default entity type allowlist
    assert not any(entity.text == "Monday" for entity in result)
