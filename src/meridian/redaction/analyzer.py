from __future__ import annotations

from presidio_analyzer import AnalyzerEngine


def build_analyzer_engine() -> AnalyzerEngine:
    """constructs the presidio analyzer, loading its spacy model.

    this is comparatively expensive (real seconds, not milliseconds) -
    callers should build one instance per process and reuse it across
    every tokenize_for_external_call() invocation, not construct one per
    call.
    """
    return AnalyzerEngine()
