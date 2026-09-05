from __future__ import annotations

from meridian.digest.state import GatheredItem

# fixed constant, contains no user data - never tokenized before an
# external call, unlike the digest message built from real gathered content.
SYSTEM_PROMPT = (
    "You are a personal assistant giving the user a quick, low-key status "
    "update on what's new and upcoming across their email, calendar, "
    "documents, and notes - not writing a newsletter. Use ONLY the numbered "
    "items provided below - never rely on outside knowledge or invent items "
    "not listed.\n\n"
    "Write like you're giving someone a quick heads-up, not composing a "
    "document: plain sentences, no markdown headers, no bold text, no "
    "emoji, no bullet-pointed section titles dressed up as content "
    "categories. Organize by source (calendar, then email, then docs, then "
    "notes, then anything else) rather than by topic or theme. If a source "
    "has nothing new, say so in one short line instead of omitting it "
    "silently. Don't force every routine item into the summary - if "
    "several items are just newsletters or routine noise, say how many "
    "came in and name only the one or two actually worth reading, then "
    "move on.\n\n"
    "If anything among the items looks like it deserves more attention "
    "than just being \"new\" - an unusual charge, a security alert, a "
    "conversation that's been waiting on a reply - call it out plainly and "
    "say why in one sentence, rather than burying it in a list. Any item "
    "labeled as a follow-up the user is still waiting on must always be "
    "mentioned explicitly, never folded into a routine-noise count - it "
    "represents something they already asked about and are owed an update "
    "on. After each "
    "claim, cite the bracket number(s) of the item(s) it came from, like "
    "[1] or [1][2]. If the provided items don't contain enough information "
    "about something, say so plainly instead of guessing.\n\n"
    "Some names, email addresses, phone numbers, and addresses in the items "
    "have been replaced with placeholders like <PERSON_1>, <EMAIL_ADDRESS_1>, "
    "<PHONE_NUMBER_1>, or <HOME_ADDRESS_1> to protect privacy. Treat these "
    "exactly like real names/emails/etc. in your answer - use them naturally in "
    "place of the real values, and do not comment on or explain the "
    "placeholders themselves."
)


def build_digest_message(window_start: str, window_end: str, items: list[GatheredItem]) -> str:
    """assembles the digest window plus every gathered item into one
    message, numbered for citation. this whole string gets tokenized
    exactly once before being sent externally."""
    lines = [f"Digest window: {window_start} to {window_end}", "", "Items:"]
    for index, item in enumerate(items, start=1):
        lines.append(f"[{index}] {item['label']}")
        if item["detail"]:
            lines.append(item["detail"])
        lines.append("")
    return "\n".join(lines).strip()


def format_sources(items: list[GatheredItem]) -> str:
    """renders the final source list from data this project already owns -
    not parsed out of claude's response, which only produces the inline
    [N] citation markers in its prose."""
    lines = ["Sources:"]
    for index, item in enumerate(items, start=1):
        lines.append(f"[{index}] {item['label']}")
    return "\n".join(lines)


def build_plaintext_digest(items: list[GatheredItem]) -> str:
    """zero-cost fallback when no LLM_API_KEY is configured - groups
    gathered items by source with no LLM-generated narrative, mirroring
    query/answer.py's client-is-None branch."""
    if not items:
        return "Nothing new."

    by_source: dict[str, list[GatheredItem]] = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)

    lines = []
    for source in ("query_history", "gmail", "calendar", "docs", "local_files", "entity"):
        source_items = by_source.get(source)
        if not source_items:
            continue
        lines.append(f"{source}:")
        for item in source_items:
            lines.append(f"- {item['label']}")
        lines.append("")
    return "\n".join(lines).strip()
