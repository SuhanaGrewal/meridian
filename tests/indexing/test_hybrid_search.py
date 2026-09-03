import numpy as np

from meridian.indexing.hybrid_search import hybrid_search, reciprocal_rank_fusion
from meridian.indexing.parent_child import ChunkRecord
from meridian.indexing.store import IndexStore


def _record(text: str) -> list[ChunkRecord]:
    return [ChunkRecord(text=text, parent_text=text, position=0, is_own_parent=True)]


def test_item_in_both_lists_ranks_above_item_in_one_list():
    vector_results = [("a", 0.9), ("b", 0.8)]
    keyword_results = [("a", 5.0), ("c", 3.0)]

    fused = reciprocal_rank_fusion([vector_results, keyword_results])

    assert fused[0][0] == "a"  # appears near top of both lists


def test_higher_rank_position_contributes_more():
    vector_results = [("a", 0.9), ("b", 0.8), ("c", 0.7)]

    fused = reciprocal_rank_fusion([vector_results])

    assert [item_id for item_id, _ in fused] == ["a", "b", "c"]


def test_empty_result_lists_produce_empty_fusion():
    assert reciprocal_rank_fusion([[], []]) == []


def test_single_list_preserves_relative_order():
    results = [("x", 1.0), ("y", 0.5), ("z", 0.1)]

    fused = reciprocal_rank_fusion([results])

    assert [item_id for item_id, _ in fused] == ["x", "y", "z"]


def test_disjoint_lists_include_all_items():
    vector_results = [("a", 0.9)]
    keyword_results = [("b", 5.0)]

    fused = reciprocal_rank_fusion([vector_results, keyword_results])

    assert {item_id for item_id, _ in fused} == {"a", "b"}


def test_hybrid_search_surfaces_item_matching_both_signals(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    # matches the query embedding closely AND contains the keyword
    store.upsert_item_chunks(
        "gmail", "msg-1", _record("quarterly budget report"), [np.array([1.0, 0.0], dtype=np.float32)], {}
    )
    # matches the keyword only, embedding is unrelated
    store.upsert_item_chunks(
        "gmail", "msg-2", _record("budget"), [np.array([0.0, 1.0], dtype=np.float32)], {}
    )
    # matches the embedding only, no keyword overlap
    store.upsert_item_chunks(
        "gmail", "msg-3", _record("unrelated dinner plans"), [np.array([0.9, 0.1], dtype=np.float32)], {}
    )

    results = hybrid_search(
        store, "budget", np.array([1.0, 0.0], dtype=np.float32), k=3
    )

    assert results[0][0] == "gmail:msg-1:0000"
    result_ids = {item_id for item_id, _ in results}
    assert result_ids == {"gmail:msg-1:0000", "gmail:msg-2:0000", "gmail:msg-3:0000"}


def test_hybrid_search_respects_source_filter(tmp_path):
    store = IndexStore(tmp_path / "index.db")
    store.upsert_item_chunks(
        "gmail", "msg-1", _record("shared term"), [np.array([1.0, 0.0], dtype=np.float32)], {}
    )
    store.upsert_item_chunks(
        "docs", "doc-1", _record("shared term"), [np.array([1.0, 0.0], dtype=np.float32)], {}
    )

    results = hybrid_search(
        store, "shared", np.array([1.0, 0.0], dtype=np.float32), k=5, source="docs"
    )

    assert len(results) == 1
    assert results[0][0] == "docs:doc-1:0000"


def test_hybrid_search_on_empty_store_returns_empty_list(tmp_path):
    store = IndexStore(tmp_path / "index.db")

    results = hybrid_search(store, "anything", np.array([1.0, 0.0], dtype=np.float32), k=5)

    assert results == []
