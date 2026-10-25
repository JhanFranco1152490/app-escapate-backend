import pytest

from app.common.identifiers import (
    has_wrong_nit_check_digit,
    is_valid_document,
    nit_check_digit,
    normalize_document,
    normalize_email,
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
        ("TI", "1098221334"),
        ("TI", "10982213345"),
        ("RC", "12345678"),
        ("RC", "1098221334"),
        ("RC", "A1B2C3D4E5"),
        ("RC", "1" * 15),
        # NIT público de la DIAN y de ejemplo: nunca documentos de personas reales.
        ("NIT", "8001972684"),
        ("NIT", "9001234568"),
        ("NIT", "900000002" + "1"),
        ("NIT", "900000009" + "0"),
        pytest.param("NIT", "80019726" + "3", id="nit-with-an-eight-digit-base"),
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
        pytest.param("XX", "900123456", id="unknown-type"),
        pytest.param("TI", "109822133", id="ti-too-short"),
        pytest.param("TI", "109822133456", id="ti-too-long"),
        pytest.param("TI", "10982213A4", id="ti-with-letters"),
        pytest.param("TI", "١٠٩٨٢٢١٣٣٤", id="ti-other-alphabet-digits"),
        pytest.param("TI", "1098221334\n", id="ti-trailing-newline"),
        pytest.param("RC", "1234567", id="rc-too-short"),
        pytest.param("RC", "1" * 16, id="rc-too-long"),
        pytest.param("RC", "ÁB123456", id="rc-non-ascii-letter"),
        pytest.param("NIT", "8001972685", id="nit-wrong-check-digit"),
        pytest.param("NIT", "9001234567", id="nit-wrong-check-digit-mockup"),
        pytest.param("NIT", "80019726", id="nit-too-short"),
        pytest.param("NIT", "80019726841", id="nit-too-long"),
        pytest.param("NIT", "80019726A4", id="nit-with-letters"),
        pytest.param("NIT", "8001972684\n", id="nit-trailing-newline"),
        pytest.param("NIT", "", id="nit-empty"),
    ],
)
def test_invalid_documents(document_type, number):
    assert not is_valid_document(document_type, number)


def test_normalizing_removes_a_trailing_newline_before_validation():
    assert is_valid_document("CC", normalize_document("10901234\n"))


@pytest.mark.parametrize("raw", ["800.197.268-4", "800197268-4", "800 197 268 4", "8001972684"])
def test_a_nit_is_valid_with_or_without_separators(raw):
    assert is_valid_document("NIT", normalize_document(raw))


@pytest.mark.parametrize(
    "base, digit",
    [
        ("800197268", 4),
        ("900123456", 8),
        pytest.param("900000002", 1, id="remainder-one-is-the-digit"),
        pytest.param("900000009", 0, id="remainder-zero-is-the-digit"),
    ],
)
def test_nit_check_digit(base, digit):
    assert nit_check_digit(base) == digit


def test_only_a_well_formed_nit_can_have_a_wrong_check_digit():
    assert has_wrong_nit_check_digit("8001972685")
    assert not has_wrong_nit_check_digit("8001972684")
    # Con la forma equivocada el problema es otro: el mensaje no debe hablar del dígito.
    assert not has_wrong_nit_check_digit("80019726A4")
    assert not has_wrong_nit_check_digit("80019726")
