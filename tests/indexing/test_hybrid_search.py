from meridian.indexing.hybrid_search import reciprocal_rank_fusion


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
