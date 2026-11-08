"""Alta, edición, desactivación y activación de servicios turísticos.

Cada operación hace un solo `commit()`. El proveedor y el tipo no cambian después de crear el
servicio. Un servicio no se borra: se desactiva, y cambiar su estado también exige la versión
que se leyó.
"""

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.common.errors import NotFound, StaleVersion
from app.suppliers.errors import ServiceTypeChanged, ServiceTypeNotOffered, SupplierInactive
from app.suppliers.models import Supplier
from app.suppliers.service_attributes import stored_attributes
from app.suppliers.services.tourist_service_queries import get_tourist_service
from app.suppliers.tourist_service_models import TouristService
from app.suppliers.tourist_service_schemas import (
    TouristServiceCreate,
    TouristServiceDetail,
    TouristServiceInput,
    TouristServiceStatusChange,
    TouristServiceUpdate,
)


def _locked_supplier(session: Session, supplier_id: int) -> Supplier:
    # Bloqueada hasta el commit: si alguien desactiva el proveedor al mismo tiempo, una de las
    # dos operaciones espera a la otra y nunca queda un servicio activo en un proveedor
    # inactivo.
    statement = select(Supplier).where(Supplier.id == supplier_id).with_for_update()
    supplier = session.exec(statement).first()
    if supplier is None:
        raise NotFound()
    return supplier


def _current(session: Session, service_id: int, expected_version: int) -> TouristService:
    service = session.get(TouristService, service_id)
    if service is None:
        raise NotFound()
    # La revisión da el error claro; si otra petición guarda entre esta lectura y el commit,
    # el bloqueo optimista del modelo responde lo mismo.
    if expected_version != service.version:
        raise StaleVersion()
    return service


def _common_fields(data: TouristServiceInput) -> dict:
    return {
        "name": data.name,
        "destination": data.destination,
        "description": data.description,
        "conditions": data.conditions,
        "attributes": stored_attributes(data.attributes),
    }


def _save(session: Session, service: TouristService) -> TouristServiceDetail:
    session.add(service)
    session.commit()
    return get_tourist_service(session, service.id)


def create_tourist_service(
    session: Session, actor: UserAccount, supplier_id: int, data: TouristServiceCreate
) -> TouristServiceDetail:
    supplier = _locked_supplier(session, supplier_id)
    if not supplier.is_active:
        raise SupplierInactive()
    # Solo se revisa al crear: si después le quitan la clasificación al proveedor, sus
    # servicios de ese tipo se conservan.
    if data.service_type not in supplier.categories:
        raise ServiceTypeNotOffered(data.service_type)
    service = TouristService(
        supplier_id=supplier.id,
        service_type=data.service_type,
        created_by_id=actor.id,
        **_common_fields(data),
    )
    return _save(session, service)


def update_tourist_service(
    session: Session, service_id: int, data: TouristServiceUpdate
) -> TouristServiceDetail:
    service = _current(session, service_id, data.expected_version)
    if data.service_type != service.service_type:
        raise ServiceTypeChanged()
    for name, value in _common_fields(data).items():
        setattr(service, name, value)
    return _save(session, service)


def deactivate_tourist_service(
    session: Session, actor: UserAccount, service_id: int, data: TouristServiceStatusChange
) -> TouristServiceDetail:
    service = _current(session, service_id, data.expected_version)
    if not service.is_active:
        return get_tourist_service(session, service.id)
    service.is_active = False
    service.deactivated_at = datetime.now(timezone.utc)
    # La relación y no el id: si ya estuviera cargada, al guardar pisaría el id.
    service.deactivated_by = actor
    return _save(session, service)


def activate_tourist_service(
    session: Session, service_id: int, data: TouristServiceStatusChange
) -> TouristServiceDetail:
    service = _current(session, service_id, data.expected_version)
    if service.is_active:
        return get_tourist_service(session, service.id)
    if not _locked_supplier(session, service.supplier_id).is_active:
        raise SupplierInactive()
    service.is_active = True
    service.deactivated_at = None
    service.deactivated_by = None
    return _save(session, service)
