from __future__ import annotations

from typing import Any

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
