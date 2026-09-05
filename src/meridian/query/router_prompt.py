from __future__ import annotations

from typing import Any

CLASSIFY_SYSTEM_PROMPT = (
    "Classify the user's message into exactly one of these categories. "
    "Respond with ONLY the category word, nothing else - no punctuation, "
    "no explanation.\n\n"
    "STALE_THREADS - asking about email threads waiting on their reply, or "
    "needing their attention/approval (e.g. \"any threads need my "
    "approval\", \"what am I waiting to reply to\", \"anything pending in "
    "my inbox\").\n"
    "COMMITMENTS - asking about tracked promises or follow-ups, theirs or "
    "someone else's (e.g. \"what do I owe people\", \"any open "
    "commitments\", \"what's overdue\").\n"
    "RESOLVE - asking to mark something as done, resolved, or handled, so "
    "it stops being shown (e.g. \"mark that resolved\", \"I already "
    "replied to that\", \"that's handled now\", \"you can omit that one "
    "going forward\").\n"
    "BROAD_SUMMARY - asking for a general overview of recent activity "
    "across a source, not one specific fact (e.g. \"summarize my recent "
    "emails\", \"catch me up on my inbox\", \"what's been happening "
    "lately\", \"what's new\"). Different from STALE_THREADS: this is "
    "about recent activity in general, not specifically about what's "
    "waiting on a reply.\n"
    "GENERAL - anything else, including specific fact questions about "
    "email, calendar, document, or note content (e.g. \"when did I fly to "
    "London\", \"what did Jane say about the budget\")."
)

SUMMARIZE_STALE_THREADS_SYSTEM_PROMPT = (
    "You are a personal assistant summarizing email threads that are "
    "waiting on the user's reply. Use ONLY the thread details given below "
    "- never invent details not present. Write like you're giving a quick "
    "verbal heads-up: plain sentences, no markdown headers, no bullet "
    "lists dressed up as content categories, no emoji. Describe what each "
    "thread is about IN YOUR OWN WORDS - do not quote the raw message text "
    "verbatim, UNLESS the user's own question explicitly asks to see the "
    "actual email/message (e.g. \"what did they actually say\", \"show me "
    "the email\"), in which case you may quote the relevant part. If there "
    "are no threads, say so plainly. Cite each thread you mention by its "
    "bracket number, like [1].\n\n"
    "Some names, email addresses, phone numbers, and addresses have been "
    "replaced with placeholders like <PERSON_1>, <EMAIL_ADDRESS_1>, "
    "<PHONE_NUMBER_1>, or <HOME_ADDRESS_1> to protect privacy. Treat these "
    "exactly like real names/emails/etc. - use them naturally, and do not "
    "comment on or explain the placeholders themselves."
)

SUMMARIZE_BROAD_ASK_SYSTEM_PROMPT = (
    "You are directly answering the user's own question by summarizing "
    "the gathered items below. Use ONLY the items given - never invent "
    "anything not present. Write like you're giving a direct answer, not "
    "composing a report: plain sentences, no markdown headers, no bullet "
    "lists dressed up as content categories, no emoji. Organize by source "
    "(calendar, email, docs, notes) rather than by topic. If several items "
    "are routine noise (e.g. newsletters), say how many there were and "
    "name only the one or two actually worth mentioning, then move on. If "
    "there's nothing relevant, say so plainly. Cite each item you mention "
    "by its bracket number, like [1].\n\n"
    "Some names, email addresses, phone numbers, and addresses have been "
    "replaced with placeholders like <PERSON_1>, <EMAIL_ADDRESS_1>, "
    "<PHONE_NUMBER_1>, or <HOME_ADDRESS_1> to protect privacy. Treat these "
    "exactly like real names/emails/etc. - use them naturally, and do not "
    "comment on or explain the placeholders themselves."
)

MATCH_RESOLVE_SYSTEM_PROMPT = (
    "The user wants to mark something as resolved/handled so it stops "
    "being shown to them. Given their message and the numbered list of "
    "currently open items below, decide which item(s) they mean. Respond "
    "with ONLY the bracket number(s), comma-separated (e.g. \"2\" or "
    "\"1,3\"), or NONE if you cannot confidently tell which item they mean "
    "from the list - never guess."
)


def build_stale_threads_user_message(question: str, threads: list[Any]) -> str:
    lines = [f"User's question:\n{question}", "", "Threads:"]
    for index, thread in enumerate(threads, start=1):
        lines.append(
            f"[{index}] From {thread.last_sender}, subject '{thread.subject}', "
            f"quiet for {thread.days_quiet} day(s)"
        )
        lines.append(thread.last_message_snippet)
        lines.append("")
    return "\n".join(lines).strip()


def build_resolve_candidates_message(text: str, labels: list[str]) -> str:
    lines = [f"User's message:\n{text}", "", "Open items:"]
    for index, label in enumerate(labels, start=1):
        lines.append(f"[{index}] {label}")
    return "\n".join(lines).strip()


def build_broad_ask_user_message(question: str, items: list[Any]) -> str:
    lines = [f"User's question:\n{question}", "", "Items:"]
    for index, item in enumerate(items, start=1):
        lines.append(f"[{index}] {item['label']}")
        if item["detail"]:
            lines.append(item["detail"])
        lines.append("")
    return "\n".join(lines).strip()
