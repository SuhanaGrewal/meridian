from presidio_analyzer import AnalyzerEngine

from meridian.redaction.analyzer import build_analyzer_engine


def test_build_analyzer_engine_returns_a_real_engine():
    engine = build_analyzer_engine()

    assert isinstance(engine, AnalyzerEngine)
    assert "PERSON" in engine.get_supported_entities()
