from __future__ import annotations

import numpy as np

from meridian.indexing import keyword_search, vector_search
from meridian.indexing.store import IndexStore


def reciprocal_rank_fusion(
    result_lists: list[list[tuple[str, float]]], *, k: int = 60
) -> list[tuple[str, float]]:
    """merges multiple ranked (id, score) lists into one ranked list using
    reciprocal rank fusion - combines rankings by position, not raw score,
    since vector cosine similarity and fts5's bm25 live on incomparable
    scales. an id appearing near the top of multiple lists outranks one
    that only appears in a single list."""
    scores: dict[str, float] = {}
    for results in result_lists:
        for rank, (item_id, _) in enumerate(results, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def hybrid_search(
    store: IndexStore,
    query_text: str,
    query_embedding: np.ndarray,
    *,
    k: int = 5,
    source: str | None = None,
) -> list[tuple[str, float]]:
    """combines vector similarity and keyword search into one ranked list.
    each individual search fetches more than k candidates so a chunk that
    ranks lower in one but higher in the other still has a chance to
    surface after fusion, before the final result is truncated to k."""
    candidate_pool = k * 2
    vector_results = vector_search.search(store, query_embedding, k=candidate_pool, source=source)
    keyword_results = keyword_search.search(store, query_text, k=candidate_pool, source=source)

    fused = reciprocal_rank_fusion([vector_results, keyword_results])
    return fused[:k]
