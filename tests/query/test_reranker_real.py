import pytest

from meridian.query.reranker import build_reranker, rerank

try:
    _reranker = build_reranker()
except Exception as exc:  # pragma: no cover - depends on model download/network
    _reranker = None
    _skip_reason = f"cross-encoder model not available: {exc}"


@pytest.fixture(scope="module")
def reranker():
    if _reranker is None:
        pytest.skip(_skip_reason)
    return _reranker


def test_real_reranker_scores_relevant_text_higher(reranker):
    question = "What is the capital of France?"
    texts = [
        "Paris is the capital and most populous city of France.",
        "Bananas are a good source of potassium.",
    ]

    scores = rerank(reranker, question, texts)

    assert scores[0] > scores[1]
    assert scores[0] > 0.5
    assert scores[1] < 0.5
