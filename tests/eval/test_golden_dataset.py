from tests.eval.golden_dataset import GOLDEN_DOCS, GOLDEN_QUESTIONS, chunk_id_for

_ALL_DOC_CHUNK_IDS = {chunk_id_for(doc) for doc in GOLDEN_DOCS}
_DOC_TOPICS = {doc.topic for doc in GOLDEN_DOCS}


def test_every_relevant_chunk_id_resolves_to_a_real_doc():
    for question in GOLDEN_QUESTIONS:
        unresolved = question.relevant_chunk_ids - _ALL_DOC_CHUNK_IDS
        assert not unresolved, f"{question.question!r} references missing docs: {unresolved}"


def test_every_non_abstain_question_topic_matches_a_doc():
    for question in GOLDEN_QUESTIONS:
        if question.should_abstain:
            continue
        assert question.topic in _DOC_TOPICS, f"{question.question!r} has no matching doc topic"


def test_every_abstain_question_has_no_relevant_docs():
    for question in GOLDEN_QUESTIONS:
        if not question.should_abstain:
            continue
        assert question.relevant_chunk_ids == frozenset()


def test_every_abstain_question_topic_is_unused_by_any_doc():
    for question in GOLDEN_QUESTIONS:
        if not question.should_abstain:
            continue
        assert question.topic not in _DOC_TOPICS, f"{question.topic!r} should not appear in any doc"


def test_doc_source_and_item_ids_are_unique():
    keys = [(doc.source, doc.item_id) for doc in GOLDEN_DOCS]
    assert len(keys) == len(set(keys))


def test_non_abstain_questions_have_at_least_one_relevant_doc():
    for question in GOLDEN_QUESTIONS:
        if question.should_abstain:
            continue
        assert question.relevant_chunk_ids
