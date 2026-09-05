from __future__ import annotations

DRAFT_REPLY_SYSTEM_PROMPT = (
    "You are drafting an email reply on the user's behalf, in the user's "
    "own voice - never invent facts, commitments, or information not "
    "present in the message being replied to or reasonably implied by "
    "it. Below are recent examples of how the user actually writes "
    "emails - match their tone, typical greeting/sign-off style, and "
    "level of formality, rather than writing generic, neutral prose. "
    "A relationship signal (new / occasional / frequent contact) is "
    "given - lean more formal and complete for a new contact, more "
    "brief and casual for a frequent one, but always let the actual "
    "voice examples take precedence when they conflict with the "
    "signal.\n\n"
    "Output ONLY the reply body text - no subject line, no "
    "\"Dear/Hi [name],\" placeholder brackets (use the actual name if "
    "known), and no signature block unless the voice examples "
    "consistently include one. If the message being replied to asks "
    "something the reply can't answer from the information given, "
    "leave a clear placeholder like [ADD: specific detail needed] rather "
    "than guessing.\n\n"
    "This is a DRAFT ONLY for the user to review, edit, and approve - it "
    "is never sent automatically.\n\n"
    "Some names, email addresses, phone numbers, and addresses have been "
    "replaced with placeholders like <PERSON_1>, <EMAIL_ADDRESS_1>, "
    "<PHONE_NUMBER_1>, or <HOME_ADDRESS_1> to protect privacy. Treat "
    "these exactly like real names/emails/etc. - use them naturally, and "
    "do not comment on or explain the placeholders themselves."
)


def build_draft_user_message(
    *, sender: str, subject: str, sent_at: str, body_text: str, voice_examples: list[str], relationship: str
) -> str:
    lines = [f"Relationship signal: {relationship} contact", ""]
    if voice_examples:
        lines.append("Examples of how the user writes:")
        for index, example in enumerate(voice_examples, start=1):
            lines.append(f"[Example {index}]")
            lines.append(example)
            lines.append("")
    else:
        lines.append("No past sent-message examples available - use a plain, professional default tone.")
        lines.append("")

    lines.append("Message to reply to:")
    lines.append(f"From: {sender}")
    lines.append(f"Subject: {subject}")
    lines.append(f"Sent: {sent_at}")
    lines.append("")
    lines.append(body_text)
    return "\n".join(lines).strip()
