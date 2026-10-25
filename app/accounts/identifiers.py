import re

_PHONE_SEPARATORS = re.compile(r"[\s.\-()]")
_PHONE = re.compile(r"3[0-9]{9}\Z")


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
