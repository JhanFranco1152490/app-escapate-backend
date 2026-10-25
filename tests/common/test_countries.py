import re

from app.common.countries import COUNTRY_CODES


def test_there_is_one_code_per_iso_country():
    assert len(COUNTRY_CODES) == 249
    assert all(re.fullmatch(r"[A-Z]{2}", code) for code in COUNTRY_CODES)


def test_the_countries_the_agency_works_with_are_there():
    assert {"CO", "VE", "US", "ES", "PA", "EC", "PE", "MX"} <= COUNTRY_CODES


def test_codes_that_are_not_countries_are_not_there():
    assert not {"XX", "EU", "UK", "co"} & COUNTRY_CODES
