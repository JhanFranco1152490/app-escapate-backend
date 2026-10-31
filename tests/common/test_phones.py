import pytest

from app.common.phones import normalize_international_phone


@pytest.mark.parametrize(
    "raw",
    [
        "3001112233",
        "300 111 2233",
        "+57 300 111 2233",
        "(+57) 300-111-2233",
        "573001112233",
    ],
)
def test_a_colombian_mobile_is_the_same_number_however_it_is_written(raw):
    assert normalize_international_phone(raw) == "+573001112233"


@pytest.mark.parametrize(
    "raw, expected",
    [
        pytest.param("+58 412 555 0101", "+584125550101", id="venezuela"),
        pytest.param("+1 202 555 0143", "+12025550143", id="united-states"),
        pytest.param("+34 612 345 678", "+34612345678", id="spain"),
    ],
)
def test_a_foreign_number_is_kept_with_its_country_code(raw, expected):
    assert normalize_international_phone(raw) == expected


def test_a_colombian_landline_is_accepted_for_clients():
    # A diferencia de los empleados, un cliente (o una empresa) puede dar un fijo.
    assert normalize_international_phone("601 234 5678") == "+576012345678"


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("+57 300 111 223", id="colombian-mobile-missing-a-digit"),
        pytest.param("12345", id="too-short"),
        pytest.param("abc", id="letters"),
        pytest.param("", id="empty"),
        pytest.param("+57 300 111 2233" + " " * 10, id="longer-than-25-characters"),
    ],
)
def test_invalid_phones_are_rejected(raw):
    assert normalize_international_phone(raw) is None
