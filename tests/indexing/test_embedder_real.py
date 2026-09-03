import numpy as np
import pytest

from meridian.indexing.embedder import build_embedder, embed_chunks
from meridian.indexing.vector_search import cosine_similarity_top_k

try:
    _embedder = build_embedder()
except Exception as exc:  # pragma: no cover - depends on model download/network
    _embedder = None
    _skip_reason = f"sentence-transformers model not available: {exc}"


@pytest.fixture(scope="module")
def embedder():
    if _embedder is None:
        pytest.skip(_skip_reason)
    return _embedder


def test_real_embedding_has_expected_dimension(embedder):
    result = embed_chunks(embedder, ["hello world"])

    assert len(result) == 1
    assert len(result[0]) == 384


def test_near_duplicate_sentences_score_highly_similar(embedder):
    texts = [
        "The cat sat on the mat.",
        "A cat was sitting on the mat.",
        "Stock markets fell sharply today.",
    ]
    vectors = np.array(embed_chunks(embedder, texts), dtype=np.float32)

    results = cosine_similarity_top_k(vectors[0], vectors[1:], k=2)

    assert results[0][0] == 0  # the near-duplicate sentence ranks first
    assert results[0][1] > results[1][1]
    assert results[0][1] > 0.5
