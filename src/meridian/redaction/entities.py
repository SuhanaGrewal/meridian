# entity type sets confirmed against a real AnalyzerEngine().get_supported_entities()
# call (presidio-analyzer 2.2, en_core_web_lg) rather than assumed from docs:
# ['CREDIT_CARD', 'CRYPTO', 'DATE_TIME', 'EMAIL_ADDRESS', 'IBAN_CODE',
#  'IP_ADDRESS', 'LOCATION', 'MAC_ADDRESS', 'MEDICAL_LICENSE', 'NRP',
#  'PERSON', 'PHONE_NUMBER', 'UK_NHS', 'URL', 'US_BANK_NUMBER',
#  'US_DRIVER_LICENSE', 'US_ITIN', 'US_PASSPORT', 'US_SSN']

# entities presidio's own analyzer is asked to detect (excludes LOCATION,
# DATE_TIME, URL, NRP - usually needed context, not sensitive identifiers).
PRESIDIO_ENTITIES = {
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "CRYPTO",
    "IBAN_CODE",
    "IP_ADDRESS",
    "MAC_ADDRESS",
    "MEDICAL_LICENSE",
    "UK_NHS",
    "US_BANK_NUMBER",
    "US_DRIVER_LICENSE",
    "US_ITIN",
    "US_PASSPORT",
    "US_SSN",
}

# tokenized with a unique numbered placeholder and recorded in the mapping -
# a draft reply may legitimately need these substituted back (e.g. "hi john",
# confirming a phone number or delivery address).
REVERSIBLE_ENTITIES = {"PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "HOME_ADDRESS"}

# replaced with a fixed, non-reversible marker - never added to the mapping,
# so there is no way for the real value to reappear even in a response.
HARD_SECRET_ENTITIES = {
    "CREDIT_CARD",
    "CRYPTO",
    "IBAN_CODE",
    "IP_ADDRESS",
    "MAC_ADDRESS",
    "MEDICAL_LICENSE",
    "UK_NHS",
    "US_BANK_NUMBER",
    "US_DRIVER_LICENSE",
    "US_ITIN",
    "US_PASSPORT",
    "US_SSN",
    "API_KEY_OR_PASSWORD",
}

ALL_ENTITIES = REVERSIBLE_ENTITIES | HARD_SECRET_ENTITIES
