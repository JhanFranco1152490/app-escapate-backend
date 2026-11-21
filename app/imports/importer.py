"""Carga inicial desde CSV de clientes y proveedores. Cada fila pasa por el mismo esquema y el
mismo servicio de alta que usa la API, así que valen las mismas reglas.

Pensado para datos que llegan incompletos o desordenados: una fila con errores no detiene las
demás, y una fila cuyo documento ya está registrado se omite en vez de duplicarse. El informe
dice el número de fila y el campo de cada error, sin repetir los datos de la persona.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.clients.models import Client
from app.clients.schemas import ClientCreate
from app.clients.services.client_management import create_client
from app.common.errors import ApiError
from app.common.seeding import same_document
from app.imports.csv_rows import CsvRow
from app.suppliers.models import Supplier
from app.suppliers.schemas import SupplierCreate
from app.suppliers.services.supplier_management import create_supplier


class RowStatus(StrEnum):
    CREATED = "creada"
    SKIPPED = "omitida"
    INVALID = "con errores"
    # En una prueba sin guardar: la fila se crearía.
    VALID = "válida"


@dataclass(frozen=True)
class RowResult:
    number: int
    status: RowStatus
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImportKind:
    schema: type[BaseModel]
    model: type
    create: Callable[[Session, UserAccount, Any], object]
    list_columns: frozenset[str] = frozenset()
    bool_columns: frozenset[str] = frozenset()

    @property
    def columns(self) -> set[str]:
        return set(self.schema.model_fields)


IMPORT_KINDS: dict[str, ImportKind] = {
    "clients": ImportKind(
        ClientCreate, Client, create_client, bool_columns=frozenset({"data_consent"})
    ),
    "suppliers": ImportKind(
        SupplierCreate, Supplier, create_supplier, list_columns=frozenset({"categories"})
    ),
}


def _message(error: dict) -> str:
    field = ".".join(str(part) for part in error["loc"]) or "fila"
    # Los mensajes propios del sistema ya están en español; los de Pydantic por defecto, no.
    if error["type"] == "missing":
        text = "Es obligatorio."
    elif error["type"] == "enum":
        text = f"Debe ser uno de: {error['ctx']['expected']}."
    elif error["type"] == "extra_forbidden":
        text = "No aplica a este tipo de registro."
    else:
        text = error["msg"]
    return f"{field}: {text}"


def _api_messages(error: ApiError) -> tuple[str, ...]:
    if not error.fields:
        return (error.detail,)
    return tuple(f"{field}: {text}" for field, texts in error.fields.items() for text in texts)


def _document(data: BaseModel) -> tuple[str, str] | None:
    document_type = getattr(data, "document_type", None)
    document_number = getattr(data, "document_number", None)
    if document_type is None or document_number is None:
        return None
    return (str(document_type), document_number)


def import_rows(
    session: Session,
    actor: UserAccount,
    kind: ImportKind,
    rows: Iterable[CsvRow],
    dry_run: bool = False,
) -> list[RowResult]:
    results = []
    # En la prueba sin guardar nada queda en la base: los repetidos dentro del archivo se
    # reconocen aquí.
    seen: set[tuple[str, str]] = set()
    for row in rows:
        try:
            data = kind.schema(**row.values)
        except ValidationError as error:
            messages = tuple(_message(item) for item in error.errors())
            results.append(RowResult(row.number, RowStatus.INVALID, messages))
            continue
        document = _document(data)
        if document is not None:
            registered = session.exec(
                select(kind.model.id).where(same_document(kind.model, *document))
            ).first()
            if registered is not None or document in seen:
                results.append(
                    RowResult(row.number, RowStatus.SKIPPED, ("El documento ya está registrado.",))
                )
                continue
            seen.add(document)
        if dry_run:
            results.append(RowResult(row.number, RowStatus.VALID))
            continue
        try:
            kind.create(session, actor, data)
        except ApiError as error:
            session.rollback()
            results.append(RowResult(row.number, RowStatus.INVALID, _api_messages(error)))
            continue
        results.append(RowResult(row.number, RowStatus.CREATED))
    return results
