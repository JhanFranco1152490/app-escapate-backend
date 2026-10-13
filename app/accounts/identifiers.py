import re

from app.accounts.models import DocumentType

_SEPARATORS = re.compile(r"[\s.\-]")
# [0-9] y \Z en vez de \d y $: \d acepta dígitos de otros alfabetos y $ acepta un salto de
# línea final, y los dos dejarían guardar como distintos documentos que son el mismo.
_CC = re.compile(r"[0-9]{5,10}\Z")
_ALPHANUMERIC = re.compile(r"[0-9A-Z]{5,20}\Z")


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
