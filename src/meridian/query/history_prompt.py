from __future__ import annotations

CLASSIFY_WAITING_SYSTEM_PROMPT = (
    "Decide whether the user's question is asking whether something they "
    "are waiting on has happened yet - a reply, a delivery, a "
    "confirmation, a response, a decision, an update (e.g. \"did I get a "
    "reply about X\", \"has Y sent the contract yet\", \"any update on "
    "Z\"). Respond with ONLY YES or NO, nothing else. Say NO for a plain "
    "fact lookup that isn't about waiting on something (e.g. \"when is my "
    "flight\", \"what did Jane say about the budget\")."
)

CHECK_RESOLVED_SYSTEM_PROMPT = (
    "The user previously asked a question about something they were "
    "waiting on. Below is that original question and a fresh answer just "
    "found from their current data. Decide: has the awaited thing now "
    "actually happened or arrived (RESOLVED), or is it still pending, "
    "unclear, or the fresh answer doesn't actually address it (PENDING)? "
    "Respond with ONLY RESOLVED or PENDING, nothing else - never guess in "
    "favor of RESOLVED without clear evidence."
)


def build_check_resolved_message(question_text: str, fresh_answer: str) -> str:
    return f"Original question:\n{question_text}\n\nFresh answer just found:\n{fresh_answer}"
