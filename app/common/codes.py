"""Códigos con los que la agencia nombra sus registros (`SOL-0231`, `COT-0012`).

Salen del `id`: no se guardan, así que son únicos por construcción y no chocan en altas
simultáneas.
"""

import re
from dataclasses import dataclass, field

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class RecordCode:
    prefix: str
    _pattern: re.Pattern = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Hasta 18 cifras sin los ceros de la izquierda: siempre cabe en un BIGINT.
        letters = re.escape(self.prefix.rstrip("-"))
        pattern = re.compile(rf"(?:{letters}-?)?0*([1-9][0-9]{{0,17}})\Z", re.IGNORECASE)
        object.__setattr__(self, "_pattern", pattern)

    def format(self, record_id: int) -> str:
        return f"{self.prefix}{record_id:04d}"

    def parse(self, text: str) -> int | None:
        """El `id` que nombra un texto escrito por una persona (`SOL-0231`, `sol231`,
        `231`), o `None` si el texto no es un código."""
        match = self._pattern.match(_WHITESPACE.sub("", text))
        return int(match.group(1)) if match else None
