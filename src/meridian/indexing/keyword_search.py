from __future__ import annotations

from meridian.indexing.store import IndexStore


def search(store: IndexStore, query: str, *, k: int = 5, source: str | None = None) -> list[tuple[str, float]]:
    """keyword search via sqlite's built-in fts5, using its own bm25()
    ranking function. fts5's bm25() returns lower-is-better scores; these
    are negated so higher-is-better, matching vector search's cosine
    similarity direction, for easy combination in hybrid search."""
    if not query.strip():
        return []

    if source is None:
        sql = """
            SELECT c.chunk_id AS chunk_id, bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.rowid = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        params: tuple = (query, k)
    else:
        sql = """
            SELECT c.chunk_id AS chunk_id, bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.rowid = chunks_fts.rowid
            WHERE chunks_fts MATCH ? AND c.source = ?
            ORDER BY rank
            LIMIT ?
        """
        params = (query, source, k)

    rows = store.connection.execute(sql, params).fetchall()
    return [(row["chunk_id"], -row["rank"]) for row in rows]
