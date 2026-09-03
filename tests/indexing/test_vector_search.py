import numpy as np

from meridian.indexing.vector_search import cosine_similarity_top_k


def test_ranks_identical_vector_highest():
    query = np.array([1.0, 0.0], dtype=np.float32)
    embeddings = np.array(
        [
            [1.0, 0.0],   # identical -> similarity 1.0
            [0.0, 1.0],   # orthogonal -> similarity 0.0
            [-1.0, 0.0],  # opposite -> similarity -1.0
        ],
        dtype=np.float32,
    )

    results = cosine_similarity_top_k(query, embeddings, k=3)

    assert [idx for idx, _ in results] == [0, 1, 2]
    assert results[0][1] == 1.0
    assert abs(results[1][1] - 0.0) < 1e-6
    assert results[2][1] == -1.0


def test_top_k_truncates_results():
    query = np.array([1.0, 0.0], dtype=np.float32)
    embeddings = np.array(
        [[1.0, 0.0], [0.9, 0.1], [0.1, 0.9], [-1.0, 0.0]],
        dtype=np.float32,
    )

    results = cosine_similarity_top_k(query, embeddings, k=2)

    assert len(results) == 2
    assert results[0][0] == 0  # most similar first


def test_empty_embeddings_returns_empty_list():
    query = np.array([1.0, 0.0], dtype=np.float32)
    embeddings = np.zeros((0, 2), dtype=np.float32)

    assert cosine_similarity_top_k(query, embeddings, k=5) == []


def test_k_larger_than_available_rows_returns_all():
    query = np.array([1.0, 0.0], dtype=np.float32)
    embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

    results = cosine_similarity_top_k(query, embeddings, k=10)

    assert len(results) == 2


def test_zero_vector_in_matrix_does_not_crash():
    query = np.array([1.0, 0.0], dtype=np.float32)
    embeddings = np.array([[0.0, 0.0], [1.0, 0.0]], dtype=np.float32)

    results = cosine_similarity_top_k(query, embeddings, k=2)

    assert len(results) == 2
    # the real match should rank above the degenerate zero vector
    assert results[0][0] == 1


def test_similarity_is_scale_invariant():
    query = np.array([1.0, 0.0], dtype=np.float32)
    embeddings = np.array([[2.0, 0.0], [0.5, 0.0]], dtype=np.float32)

    results = cosine_similarity_top_k(query, embeddings, k=2)

    assert results[0][1] == results[1][1] == 1.0
