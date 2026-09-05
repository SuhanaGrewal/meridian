from __future__ import annotations

import re
from email.utils import parseaddr

# gmail's own category labels for mail that was never a real back-and-forth
# needing attention - a newsletter or promo isn't "waiting on you" and
# won't contain a real commitment either. CATEGORY_PERSONAL and anything
# uncategorized (the primary inbox) are left alone.
NON_ACTIONABLE_CATEGORIES = frozenset(
    {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_FORUMS"}
)

# an automated auto-reply/vacation-responder/bounce message isn't a human
# waiting on you, and won't contain a genuine commitment either, even when
# it lands straight in the primary inbox (as visa/government auto-replies
# often do) - no CATEGORY_* label catches these, so this is a separate,
# subject/sender-based heuristic. Real auto-reply detection would use the
# RFC 3834 Auto-Submitted header, but gmail ingestion doesn't currently
# capture raw headers beyond subject/from/to - this heuristic works on
# data already stored today.
_AUTO_REPLY_SUBJECT_RE = re.compile(
    r"\b(auto[- ]?reply|automatic reply|out[- ]of[- ]office|vacation (response|reply|responder)"
    r"|away from (my )?(desk|email|office)|delivery status notification|undeliverable)\b",
    re.IGNORECASE,
)
_AUTO_REPLY_SENDER_RE = re.compile(
    r"(no[-._]?reply|do[-._]?not[-._]?reply|auto[-._]?reply|mailer-daemon|postmaster)",
    re.IGNORECASE,
)


def looks_like_auto_reply(subject: str | None, sender: str | None) -> bool:
    if _AUTO_REPLY_SUBJECT_RE.search(subject or ""):
        return True
    _, sender_email = parseaddr(sender or "")
    local_part = sender_email.split("@")[0] if sender_email else ""
    return bool(_AUTO_REPLY_SENDER_RE.search(local_part))
