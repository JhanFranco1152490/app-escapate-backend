"""Alta, edición y borrado de las tarifas de un servicio.

Cada operación hace un solo `commit()`. Una tarifa sí se puede borrar: lo que la use después
copia su valor, así que borrarla no cambia nada que ya se haya cotizado.
"""

from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.common.errors import NotFound, StaleVersion
from app.suppliers.errors import ChargeUnitNotAllowed, ServiceInactive
from app.suppliers.rate_schemas import ServiceRateCreate, ServiceRateInput, ServiceRateUpdate
from app.suppliers.service_types import CHARGE_UNITS, ServiceType
from app.suppliers.services.rate_queries import get_service_rate
from app.suppliers.tourist_service_models import ServiceRate, TouristService


def _locked_service(session: Session, service_id: int) -> TouristService:
    # Bloqueado hasta el commit: si alguien desactiva el servicio al mismo tiempo, una de las
    # dos operaciones espera a la otra y un servicio inactivo nunca recibe una tarifa nueva.
    statement = select(TouristService).where(TouristService.id == service_id).with_for_update()
    service = session.exec(statement).first()
    if service is None:
        raise NotFound()
    return service


def _ensure_charge_unit(service_type: str, data: ServiceRateInput) -> None:
    if data.charge_unit not in CHARGE_UNITS[ServiceType(service_type)]:
        raise ChargeUnitNotAllowed()


def _current(
    session: Session, service_id: int, rate_id: int, expected_version: int
) -> ServiceRate:
    rate = get_service_rate(session, service_id, rate_id)
    if expected_version != rate.version:
        raise StaleVersion()
    return rate


def _fields(data: ServiceRateInput) -> dict:
    return data.model_dump(exclude={"expected_version"})


def create_service_rate(
    session: Session, actor: UserAccount, service_id: int, data: ServiceRateCreate
) -> ServiceRate:
    service = _locked_service(session, service_id)
    if not service.is_active:
        raise ServiceInactive()
    _ensure_charge_unit(service.service_type, data)
    rate = ServiceRate(tourist_service_id=service.id, created_by_id=actor.id, **_fields(data))
    session.add(rate)
    session.commit()
    return get_service_rate(session, service_id, rate.id)


def update_service_rate(
    session: Session, service_id: int, rate_id: int, data: ServiceRateUpdate
) -> ServiceRate:
    rate = _current(session, service_id, rate_id, data.expected_version)
    # Las tarifas de un servicio inactivo se pueden corregir: lo que no recibe son tarifas
    # nuevas.
    _ensure_charge_unit(rate.tourist_service.service_type, data)
    for name, value in _fields(data).items():
        setattr(rate, name, value)
    session.add(rate)
    session.commit()
    return get_service_rate(session, service_id, rate.id)


def delete_service_rate(
    session: Session, service_id: int, rate_id: int, expected_version: int
) -> None:
    rate = _current(session, service_id, rate_id, expected_version)
    session.delete(rate)
    session.commit()
