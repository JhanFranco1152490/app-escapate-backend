import re
from collections.abc import Callable

_SEPARATORS = re.compile(r"[\s.\-]")
# [0-9] y \Z en vez de \d y $: \d acepta dígitos de otros alfabetos y $ acepta un salto de
# línea final, y los dos dejarían guardar como distintos documentos que son el mismo.
_NUMERIC = re.compile(r"[0-9]{5,10}\Z")
_ALPHANUMERIC = re.compile(r"[0-9A-Z]{5,20}\Z")
# Tarjeta de identidad: el NUIP de 10 dígitos, u 11 en las más antiguas.
_TI = re.compile(r"[0-9]{10,11}\Z")
# Registro civil: el NUIP actual es numérico, pero los registros antiguos traen un serial con
# letras; rechazarlos impediría registrar a esos niños.
_RC = re.compile(r"[0-9A-Z]{8,15}\Z")
# NIT completo: la base y, al final, el dígito de verificación.
_NIT = re.compile(r"[0-9]{9,10}\Z")
# Identificación tributaria de otro país (EIN, RFC, RUC...): cada país tiene su formato, así
# que solo se exige un largo razonable. Pierde el guion como los demás documentos, para que
# el mismo número escrito con o sin él no quede guardado dos veces.
_FOREIGN = re.compile(r"[0-9A-Z]{3,30}\Z")

# Pesos oficiales de la DIAN, del dígito de la derecha hacia la izquierda.
_NIT_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


def nit_check_digit(base: str) -> int:
    """Dígito de verificación de un NIT (módulo 11 con los pesos de la DIAN)."""
    total = sum(
        int(digit) * weight for digit, weight in zip(reversed(base), _NIT_WEIGHTS, strict=False)
    )
    remainder = total % 11
    return remainder if remainder < 2 else 11 - remainder


def has_wrong_nit_check_digit(number: str) -> bool:
    """Un NIT con la forma correcta pero el dígito de verificación equivocado: el error más
    común al copiarlo, que merece su propio mensaje."""
    return bool(_NIT.match(number)) and nit_check_digit(number[:-1]) != int(number[-1])


def _is_valid_nit(number: str) -> bool:
    return bool(_NIT.match(number)) and not has_wrong_nit_check_digit(number)


# Cada tipo de documento con la regla de su número ya normalizado. Cada dominio decide qué
# tipos acepta; aquí solo vive cómo se valida cada uno.
DOCUMENT_RULES: dict[str, Callable[[str], bool]] = {
    "CC": lambda number: bool(_NUMERIC.match(number)),
    "CE": lambda number: bool(_ALPHANUMERIC.match(number)),
    "PPT": lambda number: bool(_ALPHANUMERIC.match(number)),
    "PA": lambda number: bool(_ALPHANUMERIC.match(number)),
    "TI": lambda number: bool(_TI.match(number)),
    "RC": lambda number: bool(_RC.match(number)),
    "NIT": _is_valid_nit,
    "FOREIGN": lambda number: bool(_FOREIGN.match(number)),
}


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_document(value: str) -> str:
    return _SEPARATORS.sub("", value).upper()


def is_valid_document(document_type: str, number: str) -> bool:
    """Valida un número ya normalizado; un tipo sin regla es inválido."""
    rule = DOCUMENT_RULES.get(document_type)
    return rule is not None and rule(number)
