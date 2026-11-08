"""Piezas comunes de la carga de datos de demostración."""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import ColumnElement
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
    label: str,
    exists: ColumnElement[bool],
    create: Callable[[], object],
) -> SeededRecord:
    """Crea el registro; si ya hay uno que cumple `exists`, lo omite en vez de fallar.
    `label` es lo que identifica al registro en el informe de la carga.

    Se mira antes de crear y no se atrapa el error del servicio: un registro repetido puede
    fallar por más de un motivo a la vez (el documento y otra regla) y entonces el error no es
    el de documento repetido.
    """
    if session.exec(select(model.id).where(exists)).first() is not None:
        return SeededRecord(kind, label, created=False)
    create()
    return SeededRecord(kind, label, created=True)


def same_document(model: type, document_type: str, document_number: str) -> ColumnElement[bool]:
    return (model.document_type == document_type) & (model.document_number == document_number)
