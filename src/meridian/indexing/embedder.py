from __future__ import annotations

from typing import Any

from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = "all-MiniLM-L6-v2"


def build_embedder(model_name: str = DEFAULT_MODEL) -> SentenceTransformer:
    """loads the sentence-transformers model, downloading it to the local
    huggingface cache on first use. comparatively expensive (real seconds
    plus a one-time download) - callers should build one instance per
    process and reuse it across every embed_chunks() call, same injection
    pattern as build_analyzer_engine() in redaction."""
    return SentenceTransformer(model_name)


def embed_chunks(embedder: Any, texts: list[str], *, batch_size: int = 32) -> list[list[float]]:
    """embeds a list of chunk texts in batches - .encode() natively batches
    multiple texts per forward pass, so this is not extra complexity versus
    encoding one at a time, just not looping."""
    if not texts:
        return []
    return embedder.encode(texts, batch_size=batch_size, show_progress_bar=False).tolist()
