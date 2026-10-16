import pytest

from app.accounts.identifiers import (
    is_valid_document,
    is_valid_phone,
    normalize_document,
    normalize_email,
    normalize_phone,
)


def test_email_is_trimmed_and_lowercased():
    assert normalize_email("  Ana.Rojas@Gmail.COM ") == "ana.rojas@gmail.com"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1.090.123.456", "1090123456"),
        ("1090-123-456", "1090123456"),
        (" 1090 123 456 ", "1090123456"),
        ("ab123456", "AB123456"),
    ],
)
def test_document_separators_are_removed_and_letters_uppercased(raw, expected):
    assert normalize_document(raw) == expected


@pytest.mark.parametrize(
    "document_type, number",
    [
        ("CC", "12345"),
        ("CC", "1090123456"),
        ("CE", "AB12345"),
        ("PPT", "4567891"),
        ("PA", "AB1234567"),
    ],
)
def test_valid_documents(document_type, number):
    assert is_valid_document(document_type, number)


@pytest.mark.parametrize(
    "document_type, number",
    [
        pytest.param("CC", "1234", id="cc-too-short"),
        pytest.param("CC", "12345678901", id="cc-too-long"),
        pytest.param("CC", "AB12345", id="cc-with-letters"),
        pytest.param("CC", "١٢٣٤٥٦", id="other-alphabet-digits"),
        pytest.param("CC", "12345\n", id="trailing-newline-not-normalized"),
        pytest.param("PA", "ÁB12345", id="non-ascii-letter"),
        pytest.param("PA", "A" * 21, id="too-long"),
        pytest.param("CC", "", id="empty"),
        pytest.param("NIT", "900123456", id="unknown-type"),
    ],
)
def test_invalid_documents(document_type, number):
    assert not is_valid_document(document_type, number)


def test_normalizing_removes_a_trailing_newline_before_validation():
    assert is_valid_document("CC", normalize_document("10901234\n"))


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
