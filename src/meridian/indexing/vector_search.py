from __future__ import annotations

import numpy as np


def cosine_similarity_top_k(
    query_embedding: np.ndarray, embeddings: np.ndarray, *, k: int
) -> list[tuple[int, float]]:
    """returns (index, score) pairs for the top-k most similar rows in
    `embeddings` (shape (n, dim)) to query_embedding (shape (dim,)), sorted
    by descending cosine similarity. exact, brute-force - a single matrix
    multiply, comfortably fast at personal-corpus scale (thousands of
    chunks), and more accurate than an approximate index since nothing is
    being approximated."""
    if embeddings.shape[0] == 0:
        return []

    query_norm = np.linalg.norm(query_embedding)
    query_unit = query_embedding / query_norm if query_norm else query_embedding

    matrix_norms = np.linalg.norm(embeddings, axis=1)
    matrix_norms[matrix_norms == 0] = 1.0
    normalized = embeddings / matrix_norms[:, None]

    scores = normalized @ query_unit

    top_k = min(k, len(scores))
    top_indices = np.argpartition(-scores, top_k - 1)[:top_k]
    top_indices = top_indices[np.argsort(-scores[top_indices])]

    return [(int(i), float(scores[i])) for i in top_indices]
