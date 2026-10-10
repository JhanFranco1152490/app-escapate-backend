import pytest

from app.accounts.passwords import password_problems

EMAIL = "ana@example.com"
DOCUMENT = "1090123456"


def problems(password: str) -> list[str]:
    return password_problems(password, email=EMAIL, document_number=DOCUMENT)


def test_a_long_password_without_special_characters_is_accepted():
    assert problems("cafe con pan de bono") == []


@pytest.mark.parametrize("password", ["a" * 11, "", " " * 11])
def test_shorter_than_twelve_characters_is_rejected(password):
    assert problems(password) == ["La contraseña debe tener al menos 12 caracteres."]


def test_longer_than_256_characters_is_rejected():
    assert problems("a" * 257) == ["La contraseña no puede tener más de 256 caracteres."]


def test_exactly_the_limits_is_accepted():
    assert problems("a" * 12) == []
    assert problems("a" * 256) == []


SAME_AS_IDENTITY = ["La contraseña no puede ser tu correo ni tu documento."]


@pytest.mark.parametrize("password", [EMAIL, EMAIL.upper(), f" {EMAIL} "])
def test_password_equal_to_the_email_is_rejected(password):
    assert problems(password) == SAME_AS_IDENTITY


def test_password_equal_to_a_long_document_is_rejected():
    # Solo un pasaporte llega a 12 caracteres; una cédula nunca alcanza el mínimo.
    problems_found = password_problems("ab1234567890", email=EMAIL, document_number="AB1234567890")

    assert problems_found == SAME_AS_IDENTITY


def test_password_that_only_contains_the_document_is_accepted():
    assert problems(f"mi documento es {DOCUMENT}") == []
