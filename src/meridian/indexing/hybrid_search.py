from __future__ import annotations


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
