"""El código con el que la agencia nombra una solicitud (`SOL-0231`).

Sale del `id`: no se guarda, así que es único por construcción y no choca en altas
simultáneas.
"""

import re

PREFIX = "SOL-"

_WHITESPACE = re.compile(r"\s+")
# Hasta 18 cifras sin los ceros de la izquierda: siempre cabe en un BIGINT.
_CODE = re.compile(r"(?:SOL-?)?0*([1-9][0-9]{0,17})\Z", re.IGNORECASE)


def format_code(request_id: int) -> str:
    return f"{PREFIX}{request_id:04d}"


def parse_code(text: str) -> int | None:
    """El `id` que nombra un texto escrito por una persona (`SOL-0231`, `sol231`, `231`), o
    `None` si el texto no es un código."""
    match = _CODE.match(_WHITESPACE.sub("", text))
    return int(match.group(1)) if match else None
