from meridian.query.reranker import sigmoid


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
