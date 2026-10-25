import re
from collections.abc import Callable

_SEPARATORS = re.compile(r"[\s.\-]")
# [0-9] y \Z en vez de \d y $: \d acepta dígitos de otros alfabetos y $ acepta un salto de
# línea final, y los dos dejarían guardar como distintos documentos que son el mismo.
_NUMERIC = re.compile(r"[0-9]{5,10}\Z")
_ALPHANUMERIC = re.compile(r"[0-9A-Z]{5,20}\Z")

# Cada tipo de documento con la regla de su número ya normalizado. Cada dominio decide qué
# tipos acepta; aquí solo vive cómo se valida cada uno.
DOCUMENT_RULES: dict[str, Callable[[str], bool]] = {
    "CC": lambda number: bool(_NUMERIC.match(number)),
    "CE": lambda number: bool(_ALPHANUMERIC.match(number)),
    "PPT": lambda number: bool(_ALPHANUMERIC.match(number)),
    "PA": lambda number: bool(_ALPHANUMERIC.match(number)),
}


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_document(value: str) -> str:
    return _SEPARATORS.sub("", value).upper()


def is_valid_document(document_type: str, number: str) -> bool:
    """Valida un número ya normalizado; un tipo sin regla es inválido."""
    rule = DOCUMENT_RULES.get(document_type)
    return rule is not None and rule(number)
