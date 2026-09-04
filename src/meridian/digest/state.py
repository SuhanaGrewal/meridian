from __future__ import annotations

from typing import TypedDict


class GatheredItem(TypedDict):
    source: str
    label: str
    detail: str


class DigestState(TypedDict, total=False):
    window_start: str
    window_end: str
    lookahead_end: str
    items: list[GatheredItem]
    digest_text: str
    sources_text: str
    llm_used: bool
    decision: bool
