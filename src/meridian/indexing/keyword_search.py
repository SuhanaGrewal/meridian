from __future__ import annotations

import re

from meridian.indexing.store import IndexStore

_TOKEN_RE = re.compile(r"\w+")


def _build_match_query(query: str) -> str:
    """fts5's MATCH takes its own small query-expression syntax, not raw
    text - punctuation in a natural-language question (e.g. a trailing "?")
    can trigger a syntax error in that grammar rather than being treated as
    part of the searched text. extracting word tokens and OR-ing them
    together sidesteps that entirely, and OR semantics fit keyword search
    better anyway - matching any meaningful word beats requiring all of
    them for a fuzzy natural-language query."""
    return " OR ".join(_TOKEN_RE.findall(query))


def search(store: IndexStore, query: str, *, k: int = 5, source: str | None = None) -> list[tuple[str, float]]:
    """keyword search via sqlite's built-in fts5, using its own bm25()
    ranking function. fts5's bm25() returns lower-is-better scores; these
    are negated so higher-is-better, matching vector search's cosine
    similarity direction, for easy combination in hybrid search."""
    match_query = _build_match_query(query)
    if not match_query:
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
        params: tuple = (match_query, k)
    else:
        sql = """
            SELECT c.chunk_id AS chunk_id, bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.rowid = chunks_fts.rowid
            WHERE chunks_fts MATCH ? AND c.source = ?
            ORDER BY rank
            LIMIT ?
        """
        params = (match_query, source, k)

    rows = store.connection.execute(sql, params).fetchall()
    return [(row["chunk_id"], -row["rank"]) for row in rows]
