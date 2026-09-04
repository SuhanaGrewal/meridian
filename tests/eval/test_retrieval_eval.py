from meridian.indexing.store import IndexStore
from meridian.query.retrieval import retrieve
from tests.eval.golden_dataset import (
    GOLDEN_DOCS,
    GOLDEN_QUESTIONS,
    build_golden_store,
    chunk_id_for,
    topic_vector,
)
from tests.eval.scoring import mean, precision_at_k, recall_at_k, reciprocal_rank


class _FakeReranker:
    def __init__(self, scores_by_text):
        self.scores_by_text = scores_by_text

    def predict(self, pairs):
        return [self.scores_by_text.get(text, -8.0) for _, text in pairs]


def _reranker_for(question) -> _FakeReranker:
    """scores exactly this question's relevant docs high and everything
    else low - rebuilt per question since the fake ignores question text,
    unlike production's real cross-encoder."""
    scores = {}
    for doc in GOLDEN_DOCS:
        scores[doc.text] = 8.0 if chunk_id_for(doc) in question.relevant_chunk_ids else -8.0
    return _FakeReranker(scores)


def _seeded_store(tmp_path) -> IndexStore:
    store = IndexStore(tmp_path / "index.db")
    build_golden_store(store, embed=lambda doc: topic_vector(doc.topic))
    return store


def test_golden_retrieval_meets_precision_recall_mrr_thresholds(tmp_path):
    store = _seeded_store(tmp_path)
    precisions, recalls, ranks = [], [], []

    for question in GOLDEN_QUESTIONS:
        if question.should_abstain:
            continue
        result = retrieve(
            store, question.question, topic_vector(question.topic),
            reranker=_reranker_for(question), source=question.source_filter,
        )
        retrieved_ids = [chunk.chunk_id for chunk in result.chunks]
        # R-precision: precision at k = number of relevant docs for this
        # question, not a fixed 5 - most questions have 1-3 relevant docs,
        # so precision@5 would have a hard ceiling of relevant_count/5 and
        # could never reach a meaningful threshold.
        r = len(question.relevant_chunk_ids)
        precisions.append(precision_at_k(retrieved_ids, question.relevant_chunk_ids, r))
        recalls.append(recall_at_k(retrieved_ids, question.relevant_chunk_ids, 5))
        ranks.append(reciprocal_rank(retrieved_ids, question.relevant_chunk_ids))

    assert mean(precisions) >= 0.9
    assert mean(recalls) >= 0.95
    assert mean(ranks) >= 0.95


def test_golden_abstain_questions_abstain(tmp_path):
    store = _seeded_store(tmp_path)

    for question in GOLDEN_QUESTIONS:
        if not question.should_abstain:
            continue
        result = retrieve(store, question.question, topic_vector(question.topic), reranker=_reranker_for(question))
        assert result.abstained is True
