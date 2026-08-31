from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


class DocParseError(Exception):
    pass


@dataclass(frozen=True)
class ParsedDoc:
    doc_id: str
    title: str
    content_text: str
    modified_time: str | None
    content_hash: str

_HEADING_PREFIXES = {
    "TITLE": "# ",
    "SUBTITLE": "## ",
    "HEADING_1": "# ",
    "HEADING_2": "## ",
    "HEADING_3": "### ",
    "HEADING_4": "#### ",
    "HEADING_5": "##### ",
    "HEADING_6": "###### ",
}


def _paragraph_text(paragraph: dict[str, Any]) -> str:
    return "".join(
        element.get("textRun", {}).get("content", "") for element in paragraph.get("elements", [])
    )


def _render_paragraph(paragraph: dict[str, Any]) -> str:
    text = _paragraph_text(paragraph).rstrip("\n")
    if not text:
        return ""

    style = paragraph.get("paragraphStyle", {}).get("namedStyleType")
    prefix = _HEADING_PREFIXES.get(style, "")
    if not prefix and paragraph.get("bullet") is not None:
        prefix = "- "

    return f"{prefix}{text}"


def _flatten_table(table: dict[str, Any]) -> str:
    rows = []
    for row in table.get("tableRows", []):
        cells = []
        for cell in row.get("tableCells", []):
            cell_text = _flatten_content(cell.get("content", []))
            cells.append(cell_text.replace("\n", " ").strip())
        rows.append(" | ".join(cells))
    return "\n".join(rows)


def _flatten_content(body_content: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for element in body_content:
        if "paragraph" in element:
            line = _render_paragraph(element["paragraph"])
            if line:
                lines.append(line)
        elif "table" in element:
            table_text = _flatten_table(element["table"])
            if table_text:
                lines.append(table_text)
    return "\n".join(lines)


def parse_document(raw_document: dict[str, Any], *, modified_time: str | None) -> ParsedDoc:
    try:
        doc_id = raw_document["documentId"]
    except KeyError as exc:
        raise DocParseError(f"missing required field: {exc}") from exc

    title = raw_document.get("title", "")
    body_content = raw_document.get("body", {}).get("content", [])
    content_text = _flatten_content(body_content)
    content_hash = hashlib.sha256(f"{title}\n{content_text}".encode("utf-8")).hexdigest()

    return ParsedDoc(
        doc_id=doc_id,
        title=title,
        content_text=content_text,
        modified_time=modified_time,
        content_hash=content_hash,
    )
