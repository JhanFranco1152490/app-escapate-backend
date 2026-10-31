"""Tipos de campo que comparten los esquemas de entrada de varios dominios.

Cada tipo normaliza y valida en el mismo paso: lo que se guarda es exactamente lo que se
validó. Los mensajes de error van en español, listos para mostrarse en el formulario.
"""

import unicodedata
from collections.abc import Callable
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, Field, StringConstraints
from pydantic_core import PydanticCustomError

from app.common.identifiers import (
    has_wrong_nit_check_digit,
    is_valid_document,
    normalize_document,
    normalize_email,
)
from app.common.phones import normalize_international_phone

# Cabe en BIGINT: un id mayor haría fallar la consulta en la base en vez de no encontrar nada.
RecordId = Annotated[int, Field(ge=1, le=2**63 - 1)]

NAME_MAX_LENGTH = 75
EMAIL_MAX_LENGTH = 254
DOCUMENT_MAX_LENGTH = 30

_FORBIDDEN_CATEGORIES = {"Cc", "Cf"}


def without_control_characters(text: str) -> str:
    """Un texto escrito por una persona no lleva caracteres de control (categoría Cc) ni de
    formato invisibles (Cf: ancho cero, cambio de dirección del texto), que permiten que dos
    nombres idénticos a la vista no lo sean. El NUL (0x00) ni siquiera se puede guardar en
    PostgreSQL: llegaría a la base y fallaría con un 500."""
    if any(unicodedata.category(character) in _FORBIDDEN_CATEGORIES for character in text):
        raise PydanticCustomError("invalid_characters", "Contiene caracteres que no se permiten.")
    return text


def _trimmed_text(value: str, max_length: int) -> str:
    text = value.strip()
    if len(text) > max_length:
        raise PydanticCustomError("too_long", f"Máximo {max_length} caracteres.")
    return without_control_characters(text)


def required_text(max_length: int) -> Callable[[str], str]:
    def validate(value: str) -> str:
        text = _trimmed_text(value, max_length)
        if not text:
            raise PydanticCustomError("required", "Este campo es obligatorio.")
        return text

    return validate


def optional_text(max_length: int) -> Callable[[str], str | None]:
    def validate(value: str) -> str | None:
        return _trimmed_text(value, max_length) or None

    return validate


def _email(value: str) -> str:
    candidate = normalize_email(value)
    invalid = PydanticCustomError("invalid_email", "No es un correo válido.")
    if len(candidate) > EMAIL_MAX_LENGTH:
        raise invalid
    try:
        # Solo ASCII: los Gmail lo son, y así dos escrituras unicode del mismo correo no
        # se guardan como cuentas distintas.
        return validate_email(
            candidate, check_deliverability=False, allow_smtputf8=False
        ).normalized
    except EmailNotValidError:
        raise invalid from None


def _international_phone(value: str) -> str:
    number = normalize_international_phone(value)
    if number is None:
        raise PydanticCustomError("invalid_phone", "No es un teléfono válido para ese país.")
    return number


def valid_document_number(document_type: str, value: str) -> str:
    """El número normalizado, si es válido para su tipo; cada dominio decide qué tipos acepta."""
    number = normalize_document(value) if len(value) <= DOCUMENT_MAX_LENGTH else ""
    if document_type == "NIT" and has_wrong_nit_check_digit(number):
        raise PydanticCustomError(
            "invalid_check_digit", "El dígito de verificación del NIT no coincide."
        )
    if not is_valid_document(document_type, number):
        raise PydanticCustomError("invalid_document", "No es válido para ese tipo.")
    return number


PersonName = Annotated[str, AfterValidator(required_text(NAME_MAX_LENGTH))]
Email = Annotated[str, AfterValidator(_email)]
InternationalPhone = Annotated[str, AfterValidator(_international_phone)]
City = Annotated[str, AfterValidator(optional_text(80))]
SearchText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=100),
    AfterValidator(without_control_characters),
]
