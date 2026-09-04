from meridian.entity_graph.identity import (
    PersonIdentity,
    normalize_text,
    parse_person_header,
    person_entity_id,
    text_entity_id,
)


def test_normalize_text_lowercases_and_collapses_whitespace():
    assert normalize_text("  Jane   Doe  ") == "jane doe"


def test_normalize_text_empty_string():
    assert normalize_text("") == ""


def test_parse_person_header_name_and_email():
    identity = parse_person_header("Jane Doe <jane@example.com>")

    assert identity.display_name == "Jane Doe"
    assert identity.email == "jane@example.com"


def test_parse_person_header_lowercases_email():
    identity = parse_person_header("Jane Doe <Jane@Example.com>")

    assert identity.email == "jane@example.com"


def test_parse_person_header_bare_email_only():
    identity = parse_person_header("jane@example.com")

    assert identity.display_name == "jane@example.com"
    assert identity.email == "jane@example.com"


def test_parse_person_header_empty_string():
    identity = parse_person_header("")

    assert identity.display_name == ""
    assert identity.email is None


def test_parse_person_header_malformed_no_at_sign():
    identity = parse_person_header("not an email at all")

    assert identity.email is None
    assert identity.display_name == "not an email at all"


def test_parse_person_header_quoted_display_name():
    identity = parse_person_header('"Doe, Jane" <jane@example.com>')

    assert identity.display_name == "Doe, Jane"
    assert identity.email == "jane@example.com"


def test_person_entity_id_prefers_email():
    identity = PersonIdentity(display_name="Jane Doe", email="jane@example.com")

    assert person_entity_id(identity) == "PERSON:email:jane@example.com"


def test_person_entity_id_falls_back_to_normalized_name():
    identity = PersonIdentity(display_name="Jane Doe", email=None)

    assert person_entity_id(identity) == "PERSON:name:jane doe"


def test_text_entity_id_normalizes():
    assert text_entity_id("ORG", "  Acme  Corp ") == "ORG:name:acme corp"


def test_text_entity_id_distinguishes_types():
    assert text_entity_id("GPE", "Paris") != text_entity_id("ORG", "Paris")
