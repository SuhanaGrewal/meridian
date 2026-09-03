from __future__ import annotations

import numpy as np

from meridian.indexing.store import IndexStore


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


def search(
    store: IndexStore, query_embedding: np.ndarray, *, k: int = 5, source: str | None = None
) -> list[tuple[str, float]]:
    """brute-force cosine similarity search over stored chunk embeddings,
    optionally restricted to one source. returns (chunk_id, score) pairs,
    most similar first."""
    rows = store.get_chunks_with_embeddings(source)
    if not rows:
        return []

    chunk_ids = [row["chunk_id"] for row in rows]
    embeddings = np.stack([np.frombuffer(row["embedding"], dtype=np.float32) for row in rows])

    top = cosine_similarity_top_k(np.asarray(query_embedding, dtype=np.float32), embeddings, k=k)
    return [(chunk_ids[i], score) for i, score in top]
