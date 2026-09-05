from __future__ import annotations

from typing import Any

REWRITE_FOLLOWUP_SYSTEM_PROMPT = (
    "Given the recent conversation below and a new follow-up message, "
    "rewrite the follow-up into a fully self-contained question that "
    "makes sense on its own, with no prior context - resolve pronouns "
    "and implicit references using the conversation (e.g. if the prior "
    "question was about the calendar and the follow-up is \"what about "
    "next month\", rewrite it as something like \"what's on my calendar "
    "next month\"). If the follow-up is already self-contained, return "
    "it completely unchanged. Respond with ONLY the rewritten question, "
    "nothing else - no explanation, no quotes."
)


def build_rewrite_followup_message(history: list[Any], followup_text: str) -> str:
    lines = ["Recent conversation:"]
    for turn in history:
        speaker = "User" if turn["role"] == "user" else "Assistant"
        lines.append(f"{speaker}: {turn['content']}")
    lines.append("")
    lines.append(f"New follow-up message:\n{followup_text}")
    return "\n".join(lines).strip()
