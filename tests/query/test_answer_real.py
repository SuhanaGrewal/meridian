import os

import pytest

_LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_RUN_LIVE = os.environ.get("MERIDIAN_RUN_LIVE_LLM_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not (_LLM_API_KEY and _RUN_LIVE),
    reason="live claude call - set LLM_API_KEY and MERIDIAN_RUN_LIVE_LLM_TESTS=1 to run",
)


def test_ask_generates_a_real_grounded_answer(tmp_path):
    import numpy as np

    from meridian.indexing.embedder import build_embedder
    from meridian.indexing.parent_child import ChunkRecord
    from meridian.indexing.store import IndexStore
    from meridian.query.anthropic_client import build_client
    from meridian.query.answer import ask
    from meridian.query.reranker import build_reranker
    from meridian.redaction.analyzer import build_analyzer_engine

    store = IndexStore(tmp_path / "index.db")
    embedder = build_embedder()
    vector = np.array(embedder.encode(["the sky is blue"]).tolist()[0], dtype=np.float32)
    store.upsert_item_chunks(
        "gmail",
        "msg-1",
        [ChunkRecord(text="the sky is blue", parent_text="the sky is blue", position=0, is_own_parent=True)],
        [vector],
        {"subject": "Colors", "sender": "a@example.com", "sent_at": "2024-06-12T00:00:00Z"},
    )

    client = build_client(_LLM_API_KEY)
    result = ask(
        "what color is the sky",
        store=store,
        embedder=embedder,
        reranker=build_reranker(),
        analyzer=build_analyzer_engine(),
        client=client,
        model=os.environ.get("LLM_MODEL", "claude-haiku-4-5"),
    )

    assert result.llm_configured is True
    assert not result.abstained
    assert result.answer
    assert "blue" in result.answer.lower()
    assert result.sources is not None
