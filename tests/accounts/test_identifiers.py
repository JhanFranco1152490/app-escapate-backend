import pytest

from app.accounts.identifiers import is_valid_phone, normalize_phone


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("3001234567", "3001234567"),
        ("300 123 4567", "3001234567"),
        ("300-123-4567", "3001234567"),
        ("(300) 1234567", "3001234567"),
        ("+57 300 123 4567", "3001234567"),
        ("573001234567", "3001234567"),
    ],
)
def test_phone_separators_and_country_code_are_removed(raw, expected):
    assert normalize_phone(raw) == expected


def test_a_ten_digit_phone_starting_with_57_is_not_mistaken_for_the_country_code():
    # Un celular siempre empieza por 3, así que esto ya es inválido; lo importante es que
    # no se recorte un número de 10 dígitos pensando que trae el indicativo.
    assert normalize_phone("5712345678") == "5712345678"


@pytest.mark.parametrize("number", ["3001234567", "3123456789"])
def test_valid_phones(number):
    assert is_valid_phone(number)


@pytest.mark.parametrize(
    "number",
    [
        pytest.param("6012345678", id="landline"),
        pytest.param("300123456", id="too-short"),
        pytest.param("30012345678", id="too-long"),
        pytest.param("300123456A", id="with-letters"),
        pytest.param("300123456٣", id="other-alphabet-digit"),
        pytest.param("3001234567\n", id="trailing-newline-not-normalized"),
        pytest.param("", id="empty"),
    ],
)
def test_invalid_phones(number):
    assert not is_valid_phone(number)
