"""Leer un CSV exportado de una hoja de cálculo, tal como suele llegar: con o sin BOM, separado
por coma o por punto y coma (Excel en español usa `;`), con celdas vacías y espacios de más.

Lo único que se traduce aquí es la forma de la celda (vacía, lista, sí/no); qué vale cada campo
lo decide el esquema de alta del dominio, igual que en la API.
"""

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Una lista en una sola celda: `lodging|tours`.
LIST_SEPARATOR = "|"
_TRUE = {"si", "sí", "true", "1", "x", "yes"}
_FALSE = {"no", "false", "0"}


@dataclass(frozen=True)
class CsvRow:
    # El número de la fila en la hoja, contando el encabezado como la 1.
    number: int
    values: dict[str, Any]


class CsvFormatError(Exception):
    pass


def _cell(value: str, is_list: bool, is_bool: bool) -> Any:
    text = value.strip()
    if is_list:
        return [part.strip() for part in text.split(LIST_SEPARATOR) if part.strip()]
    if is_bool and text.lower() in _TRUE | _FALSE:
        return text.lower() in _TRUE
    return text


def read_rows(
    path: Path,
    columns: set[str],
    list_columns: frozenset[str] = frozenset(),
    bool_columns: frozenset[str] = frozenset(),
) -> Iterator[CsvRow]:
    """Las filas con contenido. Una celda vacía no se manda: el esquema usa su valor por
    defecto o dice que falta. Una columna que el esquema no conoce detiene todo, para no
    perder en silencio un dato que el archivo sí traía."""
    with path.open(encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)
        file.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error as error:
            raise CsvFormatError(
                "No se reconoce el separador: usa coma o punto y coma."
            ) from error
        reader = csv.DictReader(file, dialect=dialect)
        headers = [header.strip() for header in reader.fieldnames or []]
        unknown = sorted(set(headers) - columns)
        if unknown:
            raise CsvFormatError(f"Columnas desconocidas: {', '.join(unknown)}.")
        reader.fieldnames = headers
        for number, raw in enumerate(reader, start=2):
            values = {
                name: _cell(value, name in list_columns, name in bool_columns)
                for name, value in raw.items()
                if name is not None and value is not None and value.strip()
            }
            if values:
                yield CsvRow(number, values)
