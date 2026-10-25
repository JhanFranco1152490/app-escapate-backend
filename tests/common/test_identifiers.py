import pytest

from app.common.identifiers import is_valid_document, normalize_document, normalize_email


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
