from meridian.query.reranker import rerank, sigmoid


class _FakeReranker:
    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def predict(self, pairs):
        self.calls.append(pairs)
        return self.scores


def test_sigmoid_of_zero_is_half():
    assert sigmoid(0.0) == 0.5


def test_sigmoid_of_large_positive_is_near_one():
    assert sigmoid(8.6) > 0.99


def test_sigmoid_of_large_negative_is_near_zero():
    assert sigmoid(-4.3) < 0.02


def test_sigmoid_is_monotonic():
    assert sigmoid(-1.0) < sigmoid(0.0) < sigmoid(1.0)


def test_sigmoid_output_always_between_zero_and_one():
    for x in (-100.0, -1.0, 0.0, 1.0, 100.0):
        assert 0.0 <= sigmoid(x) <= 1.0


def test_rerank_returns_sigmoid_scores_in_order():
    reranker = _FakeReranker([8.6, -4.3, 0.0])

    scores = rerank(reranker, "my question", ["doc a", "doc b", "doc c"])

    assert len(scores) == 3
    assert scores[0] > 0.99
    assert scores[1] < 0.02
    assert scores[2] == 0.5


def test_rerank_pairs_question_with_each_text():
    reranker = _FakeReranker([0.0, 0.0])

    rerank(reranker, "my question", ["doc a", "doc b"])

    assert reranker.calls == [[("my question", "doc a"), ("my question", "doc b")]]


def test_rerank_empty_texts_returns_empty_without_calling_predict():
    class _ExplodingReranker:
        def predict(self, pairs):
            raise AssertionError("should not be called for empty input")

    assert rerank(_ExplodingReranker(), "my question", []) == []
