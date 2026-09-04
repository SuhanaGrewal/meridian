from __future__ import annotations

import math
from typing import Any

from sentence_transformers import CrossEncoder

DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def build_reranker(model_name: str = DEFAULT_RERANKER_MODEL) -> CrossEncoder:
    """loads the cross-encoder reranking model, downloading it on first use.
    comparatively expensive - callers should build one instance per process
    and reuse it, same injection pattern as build_embedder()/
    build_analyzer_engine()."""
    return CrossEncoder(model_name)


def sigmoid(x: float) -> float:
    """maps a cross-encoder's raw, unbounded logit score into a calibrated
    0-1 confidence. a ms-marco-trained cross-encoder's scores are logits,
    not already a bounded probability - roughly +8.6 for a clearly relevant
    pair, -4.3 for irrelevant - so this transform is what makes an abstain
    threshold like 0.5 mean something (0.5 = logit 0 = "no more evidence of
    relevance than irrelevance")."""
    return 1.0 / (1.0 + math.exp(-x))


def rerank(reranker: Any, question: str, texts: list[str]) -> list[float]:
    """scores each text's relevance to the question, returning a calibrated
    0-1 confidence per text, in the same order as `texts`. plain text in,
    plain floats out - same shape as embed_chunks() - so callers own the
    pairing/sorting against whatever candidate objects those texts came
    from."""
    if not texts:
        return []
    pairs = [(question, text) for text in texts]
    scores = reranker.predict(pairs)
    return [sigmoid(float(score)) for score in scores]
