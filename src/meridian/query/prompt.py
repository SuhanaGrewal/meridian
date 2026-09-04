from __future__ import annotations

from meridian.query.retrieval import RetrievedChunk

# fixed constant, contains no user data - never tokenized before an
# external call, unlike the user message built from real retrieved content.
SYSTEM_PROMPT = (
    "You are a personal knowledge assistant. Answer the user's question using "
    "ONLY the numbered context blocks provided below the question - never rely "
    "on outside knowledge. After each claim, cite the bracket number(s) of the "
    "context block(s) it came from, like [1] or [1][2]. If the provided context "
    "does not contain enough information to answer, say so plainly instead of "
    "guessing.\n\n"
    "Some names, email addresses, phone numbers, and addresses in the context "
    "have been replaced with placeholders like <PERSON_1>, <EMAIL_ADDRESS_1>, "
    "<PHONE_NUMBER_1>, or <HOME_ADDRESS_1> to protect privacy. Treat these "
    "exactly like real names/emails/etc. in your answer - use them naturally in "
    "place of the real values, and do not comment on or explain the "
    "placeholders themselves."
)


def _source_label(chunk: RetrievedChunk) -> str:
    metadata = chunk.metadata
    if chunk.source == "gmail":
        return (
            f"Gmail email from {metadata.get('sender', '')}, "
            f"sent {metadata.get('sent_at', '')}, "
            f"subject: '{metadata.get('subject', '')}'"
        )
    if chunk.source == "calendar":
        return f"Calendar event '{metadata.get('summary', '')}' starting {metadata.get('start_at', '')}"
    if chunk.source == "docs":
        return f"Google Doc titled '{metadata.get('title', '')}'"
    if chunk.source == "local_files":
        return f"Note file at {metadata.get('path', '')}"
    return f"{chunk.source} item {chunk.source_item_id}"
