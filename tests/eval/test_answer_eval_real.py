import os

import pytest

_LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_RUN_LIVE = os.environ.get("MERIDIAN_RUN_LIVE_LLM_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not (_LLM_API_KEY and _RUN_LIVE),
    reason="live claude call - set LLM_API_KEY and MERIDIAN_RUN_LIVE_LLM_TESTS=1 to run",
)


def test_golden_answers_never_cite_out_of_range_sources(tmp_path):
    import numpy as np

    from meridian.indexing.embedder import build_embedder
    from meridian.indexing.store import IndexStore
    from meridian.query.anthropic_client import build_client
    from meridian.query.answer import ask
    from meridian.query.reranker import build_reranker
    from meridian.redaction.analyzer import build_analyzer_engine
    from tests.eval.golden_dataset import GOLDEN_DOCS, GOLDEN_QUESTIONS, build_golden_store
    from tests.eval.scoring import extract_citation_indices

    store = IndexStore(tmp_path / "index.db")
    embedder = build_embedder()
    doc_texts = [doc.text for doc in GOLDEN_DOCS]
    doc_vectors = embedder.encode(doc_texts).tolist()
    vector_by_item_id = {
        doc.item_id: np.array(doc_vectors[index], dtype=np.float32) for index, doc in enumerate(GOLDEN_DOCS)
    }
    build_golden_store(store, embed=lambda doc: vector_by_item_id[doc.item_id])

    client = build_client(_LLM_API_KEY)
    model = os.environ.get("LLM_MODEL", "claude-haiku-4-5")
    reranker = build_reranker()
    analyzer = build_analyzer_engine()
    non_abstain_questions = [question for question in GOLDEN_QUESTIONS if not question.should_abstain]

    for question in non_abstain_questions[:6]:  # bounded subset - keeps real API cost/time bounded
        result = ask(
            question.question,
            store=store,
            embedder=embedder,
            reranker=reranker,
            analyzer=analyzer,
            client=client,
            model=model,
        )

        assert result.llm_configured is True
        if result.abstained:
            continue  # a real cross-encoder may legitimately be pickier than the golden set's fake reranker
        indices = extract_citation_indices(result.answer)
        assert all(1 <= index <= len(result.chunks) for index in indices)
