"""Alta, edición, desactivación y activación de proveedores.

Cada operación hace un solo `commit()`. El documento es opcional, pero si se registra no
puede tenerlo otro proveedor con el mismo tipo. Un proveedor no se borra: se desactiva, y
cambiar su estado también exige la versión que se leyó, para que nadie lo haga mirando una
ficha vieja.
"""

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.common.database import database_conflicts
from app.common.errors import StaleVersion
from app.suppliers.errors import DuplicateSupplier
from app.suppliers.models import Supplier
from app.suppliers.schemas import (
    SupplierCreate,
    SupplierInput,
    SupplierStatusChange,
    SupplierUpdate,
)
from app.suppliers.services.supplier_queries import get_supplier

_CONFLICTS = {"uq_supplier_document": DuplicateSupplier}


def _ensure_document_is_free(
    session: Session, data: SupplierInput, exclude_id: int | None = None
) -> None:
    if data.document_number is None:
        return
    statement = select(Supplier.id).where(
        Supplier.document_type == data.document_type,
        Supplier.document_number == data.document_number,
    )
    if exclude_id is not None:
        statement = statement.where(Supplier.id != exclude_id)
    if session.exec(statement).first() is not None:
        raise DuplicateSupplier()


def _current(session: Session, supplier_id: int, expected_version: int) -> Supplier:
    supplier = get_supplier(session, supplier_id)
    # La revisión da el error claro; si otra petición guarda entre esta lectura y el commit,
    # el bloqueo optimista del modelo responde lo mismo.
    if expected_version != supplier.version:
        raise StaleVersion()
    return supplier


def _save(session: Session, supplier: Supplier) -> Supplier:
    with database_conflicts(session, _CONFLICTS):
        session.add(supplier)
        session.commit()
    return get_supplier(session, supplier.id)


def create_supplier(session: Session, actor: UserAccount, data: SupplierCreate) -> Supplier:
    _ensure_document_is_free(session, data)
    return _save(session, Supplier(**data.model_dump(), created_by_id=actor.id))


def update_supplier(session: Session, supplier_id: int, data: SupplierUpdate) -> Supplier:
    supplier = _current(session, supplier_id, data.expected_version)
    _ensure_document_is_free(session, data, exclude_id=supplier.id)
    # El estado y quién lo registró no se editan aquí.
    for name, value in data.model_dump(exclude={"expected_version"}).items():
        setattr(supplier, name, value)
    return _save(session, supplier)


def deactivate_supplier(
    session: Session, actor: UserAccount, supplier_id: int, data: SupplierStatusChange
) -> Supplier:
    supplier = _current(session, supplier_id, data.expected_version)
    if not supplier.is_active:
        return supplier
    supplier.is_active = False
    supplier.deactivated_at = datetime.now(timezone.utc)
    # La relación y no el id: ya viene cargada con la ficha, y al guardar pisaría el id.
    supplier.deactivated_by = actor
    return _save(session, supplier)


def activate_supplier(session: Session, supplier_id: int, data: SupplierStatusChange) -> Supplier:
    supplier = _current(session, supplier_id, data.expected_version)
    if supplier.is_active:
        return supplier
    supplier.is_active = True
    supplier.deactivated_at = None
    supplier.deactivated_by = None
    return _save(session, supplier)
