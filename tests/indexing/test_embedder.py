import numpy as np

from meridian.indexing.embedder import embed_chunks


class _FakeEmbedder:
    def __init__(self, dim: int = 3):
        self.dim = dim
        self.calls: list[dict] = []

    def encode(self, texts, batch_size=32, show_progress_bar=False):
        self.calls.append({"texts": texts, "batch_size": batch_size})
        return np.array([[float(len(t))] * self.dim for t in texts], dtype=np.float32)


def test_embed_chunks_returns_list_of_lists():
    embedder = _FakeEmbedder(dim=3)

    result = embed_chunks(embedder, ["hello", "hi"])

    assert result == [[5.0, 5.0, 5.0], [2.0, 2.0, 2.0]]


def test_embed_chunks_empty_list_returns_empty_without_calling_encode():
    class _ExplodingEmbedder:
        def encode(self, *args, **kwargs):
            raise AssertionError("should not be called for empty input")

    assert embed_chunks(_ExplodingEmbedder(), []) == []


def test_embed_chunks_passes_batch_size_through():
    embedder = _FakeEmbedder()

    embed_chunks(embedder, ["a", "b", "c"], batch_size=16)

    assert embedder.calls[0]["batch_size"] == 16


def test_embed_chunks_single_call_for_whole_list_not_looped():
    embedder = _FakeEmbedder()

    embed_chunks(embedder, ["a", "b", "c"])

    assert len(embedder.calls) == 1
    assert embedder.calls[0]["texts"] == ["a", "b", "c"]
