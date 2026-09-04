from __future__ import annotations

import math


def sigmoid(x: float) -> float:
    """maps a cross-encoder's raw, unbounded logit score into a calibrated
    0-1 confidence. a ms-marco-trained cross-encoder's scores are logits,
    not already a bounded probability - roughly +8.6 for a clearly relevant
    pair, -4.3 for irrelevant - so this transform is what makes an abstain
    threshold like 0.5 mean something (0.5 = logit 0 = "no more evidence of
    relevance than irrelevance")."""
    return 1.0 / (1.0 + math.exp(-x))
