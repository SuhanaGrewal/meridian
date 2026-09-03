from meridian.redaction.entities import (
    ALL_ENTITIES,
    HARD_SECRET_ENTITIES,
    PRESIDIO_ENTITIES,
    REVERSIBLE_ENTITIES,
)


def test_reversible_and_hard_secret_entities_are_disjoint():
    assert REVERSIBLE_ENTITIES.isdisjoint(HARD_SECRET_ENTITIES)


def test_all_entities_is_the_union():
    assert ALL_ENTITIES == REVERSIBLE_ENTITIES | HARD_SECRET_ENTITIES


def test_excluded_entities_are_not_in_presidio_entities():
    for excluded in ("LOCATION", "DATE_TIME", "URL", "NRP"):
        assert excluded not in PRESIDIO_ENTITIES


def test_custom_entities_are_not_requested_from_presidio():
    # HOME_ADDRESS and API_KEY_OR_PASSWORD come from our own regex
    # recognizers, not presidio's analyzer - it doesn't know these types.
    assert "HOME_ADDRESS" not in PRESIDIO_ENTITIES
    assert "API_KEY_OR_PASSWORD" not in PRESIDIO_ENTITIES
    assert "HOME_ADDRESS" in REVERSIBLE_ENTITIES
    assert "API_KEY_OR_PASSWORD" in HARD_SECRET_ENTITIES


def test_presidio_entities_is_subset_of_all_entities_plus_custom():
    # every presidio entity we request should be classified somewhere
    for entity in PRESIDIO_ENTITIES:
        assert entity in ALL_ENTITIES
