from __future__ import annotations

# fixed constant, contains no user data - never tokenized before an
# external call, unlike the user message built from a real email.
SYSTEM_PROMPT = (
    "You are analyzing a single email to detect a soft commitment - a "
    "promise the SENDER of THIS email makes about their OWN future action, "
    "by or before a certain time (e.g. \"I'll send the report by Friday,\" "
    "\"I'll get back to you next week\"). Use ONLY the email text given "
    "below - never invent a commitment that isn't actually there.\n\n"
    "Do NOT count: a request or ask directed at the recipient (e.g. "
    "\"please update the tracker,\" \"can you send this by Friday\" - "
    "these ask the RECIPIENT to act, they are not the sender promising "
    "anything); a question; a commitment some third party made that's "
    "merely mentioned in passing; or a generic boilerplate policy/SLA "
    "statement that's standard template text in an automated confirmation "
    "or signature block (e.g. \"we typically respond within 2 hours during "
    "business hours,\" \"our support team replies within 24 hours\") - "
    "these describe a standing policy applied to everyone, not a specific "
    "promise made to address something in this particular email. The test "
    "is always \"did the person who wrote this email promise, specifically "
    "and in response to something in this exchange, to personally do "
    "something themselves\" - if the action belongs to the recipient or "
    "anyone else, or it's a generic policy rather than something specific "
    "to this conversation, it is not a commitment.\n\n"
    "Respond in exactly this format and nothing else:\n"
    "HAS_COMMITMENT: yes or no\n"
    "DESCRIPTION: one short sentence describing what was promised (omit "
    "this line if no commitment)\n"
    "DEADLINE_PHRASE: the exact relative time phrase used, verbatim (e.g. "
    "\"by Friday\", \"next week\", \"end of day\"), or NONE if no specific "
    "deadline was given (omit this line if no commitment)\n\n"
    "Do not resolve the deadline phrase to an actual calendar date "
    "yourself - report it exactly as written and let the caller resolve "
    "it.\n\n"
    "Some names, email addresses, phone numbers, and addresses in the "
    "email have been replaced with placeholders like <PERSON_1>, "
    "<EMAIL_ADDRESS_1>, <PHONE_NUMBER_1>, or <HOME_ADDRESS_1> to protect "
    "privacy. Treat these exactly like real names/emails/etc. - use them "
    "naturally in your description, and do not comment on or explain the "
    "placeholders themselves."
)


def build_user_message(*, sender: str, subject: str, sent_at: str, body_text: str) -> str:
    return f"From: {sender}\nSubject: {subject}\nSent: {sent_at}\n\n{body_text}"
