"""Piezas comunes de la carga de datos de demostración."""

from collections.abc import Callable
from dataclasses import dataclass

from sqlmodel import Session, select


@dataclass(frozen=True)
class SeededRecord:
    kind: str
    document: str
    created: bool


def seed_if_new(
    session: Session,
    model: type,
    kind: str,
    document_type: str,
    document_number: str,
    create: Callable[[], object],
) -> SeededRecord:
    """Crea el registro; si ya hay uno con ese documento, lo omite en vez de fallar.

    Se mira antes de crear y no se atrapa el error del servicio: un registro repetido puede
    fallar por más de un motivo a la vez (el documento y otra regla) y entonces el error no es
    el de documento repetido.
    """
    document = f"{document_type} {document_number}"
    existing = select(model.id).where(
        model.document_type == document_type, model.document_number == document_number
    )
    if session.exec(existing).first() is not None:
        return SeededRecord(kind, document, created=False)
    create()
    return SeededRecord(kind, document, created=True)
