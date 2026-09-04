from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_ENTITY_TYPES = {"PERSON", "ORG", "GPE", "EVENT"}
# excludes NORP (nationality/religion/politics - noisy, not a stable
# identity), DATE/TIME/CARDINAL/ORDINAL/MONEY/PERCENT/QUANTITY (attributes,
# not linkable identities), and FAC/LAW/WORK_OF_ART/PRODUCT (out of scope
# for a personal knowledge graph's v1).


def build_ner_engine() -> Any:
    """loads spacy's own model directly, not through presidio - presidio's
    AnalyzerEngine.analyze() has no ORG/GPE/EVENT recognizer and never
    will, since it's a curated PII recognizer registry, not a passthrough
    of spacy's raw .ents. this is the same en_core_web_lg model already
    required and downloaded for phase 6's redaction, just used through
    spacy's own interface to reach its broader entity set.

    comparatively expensive (real seconds to load) - callers should build
    one instance per process and reuse it, same injection pattern as
    build_embedder()/build_reranker()/build_analyzer_engine()."""
    import spacy

    return spacy.load("en_core_web_lg")


@dataclass(frozen=True)
class ExtractedEntity:
    text: str
    label: str
    start_char: int
    end_char: int


def extract_entities(
    nlp: Any, text: str, *, entity_types: set[str] = DEFAULT_ENTITY_TYPES
) -> list[ExtractedEntity]:
    if not text.strip():
        return []
    doc = nlp(text)
    return [
        ExtractedEntity(
            text=ent.text, label=ent.label_, start_char=ent.start_char, end_char=ent.end_char
        )
        for ent in doc.ents
        if ent.label_ in entity_types
    ]
