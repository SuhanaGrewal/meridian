from __future__ import annotations

from dataclasses import dataclass
from email.utils import parseaddr


def normalize_text(value: str) -> str:
    """lowercase + collapsed whitespace - the one comparison key used
    everywhere identities are compared. documented limitation: this is
    exact matching only - "Jon Smith" will not link to "John Smith". no
    fuzzy-matching library is introduced, consistent with the project's
    dependency-conscious, hand-rolled style."""
    return " ".join(value.strip().lower().split())


@dataclass(frozen=True)
class PersonIdentity:
    display_name: str
    email: str | None


def parse_person_header(raw: str) -> PersonIdentity:
    """splits a "Name <email>" header into (display_name, email) via the
    stdlib's own address parser. falls back to using the email (or the raw
    string) as the display name when no name portion is present."""
    display_name, email_addr = parseaddr(raw or "")
    email = email_addr.strip().lower() if "@" in email_addr else None
    name = display_name.strip() or (email or raw.strip())
    return PersonIdentity(display_name=name, email=email)


def person_identity_key(identity: PersonIdentity) -> str:
    """email is the strong identity key when known; a normalized name is
    the weak fallback key for people with no known email address."""
    if identity.email:
        return f"email:{identity.email}"
    return f"name:{normalize_text(identity.display_name)}"


def person_entity_id(identity: PersonIdentity) -> str:
    return f"PERSON:{person_identity_key(identity)}"


def text_identity_key(text: str) -> str:
    """ORG/GPE/EVENT have no email concept - canonicalized purely by
    normalized text."""
    return f"name:{normalize_text(text)}"


def text_entity_id(entity_type: str, text: str) -> str:
    return f"{entity_type}:{text_identity_key(text)}"
