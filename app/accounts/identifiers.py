import re

from app.accounts.models import DocumentType

_SEPARATORS = re.compile(r"[\s.\-]")
# [0-9] y \Z en vez de \d y $: \d acepta dígitos de otros alfabetos y $ acepta un salto de
# línea final, y los dos dejarían guardar como distintos documentos que son el mismo.
_CC = re.compile(r"[0-9]{5,10}\Z")
_ALPHANUMERIC = re.compile(r"[0-9A-Z]{5,20}\Z")

_PHONE_SEPARATORS = re.compile(r"[\s.\-()]")
_PHONE = re.compile(r"3[0-9]{9}\Z")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_document(value: str) -> str:
    return _SEPARATORS.sub("", value).upper()


def is_valid_document(document_type: str, number: str) -> bool:
    """Valida un número ya normalizado."""
    if document_type == DocumentType.CC:
        return bool(_CC.match(number))
    if document_type in DocumentType.__members__.values():
        return bool(_ALPHANUMERIC.match(number))
    return False


def normalize_phone(value: str) -> str:
    """Quita separadores y, si viene con el indicativo de Colombia (+57 o 57), lo quita.

    Un celular siempre son 10 dígitos; con el indicativo suman 12, así que un "57" inicial
    solo se quita en ese caso, nunca de un número que ya tiene 10 dígitos.
    """
    digits = _PHONE_SEPARATORS.sub("", value)
    if digits.startswith("+57"):
        return digits[3:]
    if digits.startswith("57") and len(digits) == 12:
        return digits[2:]
    return digits


def is_valid_phone(number: str) -> bool:
    """Valida un número ya normalizado."""
    return bool(_PHONE.match(number))
