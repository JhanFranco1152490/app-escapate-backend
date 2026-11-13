"""Alta, edición, cierre y reapertura de solicitudes de viaje.

Cada operación hace un solo `commit()`. Una solicitud cerrada no se edita ni se vuelve a
cerrar: primero se reabre. El cliente no cambia después de crearla.
"""

from datetime import date, datetime, timezone

from sqlmodel import Session

from app.accounts.models import UserAccount
from app.clients.models import Client
from app.common.dates import today
from app.common.errors import InvalidFields, StaleVersion
from app.travel_requests.errors import (
    DATE_IN_PAST,
    INELIGIBLE_ADVISOR,
    UNKNOWN_CLIENT,
    ClientChanged,
    TravelRequestClosed,
    TravelRequestNotClosed,
)
from app.travel_requests.models import DateMode, TravelRequest, TravelRequestStatus
from app.travel_requests.schemas import (
    TravelRequestClose,
    TravelRequestCreate,
    TravelRequestInput,
    TravelRequestReopen,
    TravelRequestUpdate,
)
from app.travel_requests.services.advisors import is_eligible_advisor
from app.travel_requests.services.request_queries import get_request
from app.travel_requests.services.request_status import refresh_status


def _trip_start_check(data: TravelRequestInput) -> tuple[str, date]:
    """La fecha que dice si el viaje ya pasó: la salida, o el final del período flexible
    (mientras el período no termine, todavía se puede viajar en él)."""
    if data.date_mode == DateMode.EXACT:
        return "departure_date", data.departure_date
    return "window_end", data.window_end


def _check_references(
    session: Session, data: TravelRequestInput, current: TravelRequest | None = None
) -> None:
    """Lo que el esquema no puede revisar sin la base, con todos los errores juntos."""
    fields: dict[str, list[str]] = {}
    if current is None and session.get(Client, data.client_id) is None:
        fields["client_id"] = [UNKNOWN_CLIENT]
    if not is_eligible_advisor(session, data.assigned_to_id):
        fields["assigned_to_id"] = [INELIGIBLE_ADVISOR]

    field, day = _trip_start_check(data)
    # Al editar solo se revisa si la fecha cambió: se pueden corregir otros datos de una
    # solicitud cuyo viaje ya empezó.
    unchanged = current is not None and getattr(current, field) == day
    if not unchanged and day < today():
        fields[field] = [DATE_IN_PAST]
    if fields:
        raise InvalidFields(fields=fields)


def _current(session: Session, request_id: int, expected_version: int) -> TravelRequest:
    request = get_request(session, request_id)
    # La revisión da el error claro; si otra petición guarda entre esta lectura y el commit,
    # el bloqueo optimista del modelo responde lo mismo.
    if expected_version != request.version:
        raise StaleVersion()
    return request


def _open(session: Session, request_id: int, expected_version: int) -> TravelRequest:
    request = get_request(session, request_id)
    # Cerrada antes que versión vieja: quien vea la solicitud cerrada sabe qué hacer, y al
    # recargar se encontraría con el mismo bloqueo.
    if request.status == TravelRequestStatus.CLOSED:
        raise TravelRequestClosed()
    return _current(session, request_id, expected_version)


def _save(session: Session, request: TravelRequest) -> TravelRequest:
    session.add(request)
    session.commit()
    return get_request(session, request.id)


def create_request(
    session: Session, actor: UserAccount, data: TravelRequestCreate
) -> TravelRequest:
    _check_references(session, data)
    return _save(session, TravelRequest(**data.model_dump(), created_by_id=actor.id))


def update_request(session: Session, request_id: int, data: TravelRequestUpdate) -> TravelRequest:
    request = _open(session, request_id, data.expected_version)
    if data.client_id != request.client_id:
        raise ClientChanged()
    _check_references(session, data, current=request)

    # El estado, el cierre y quién la registró no se editan aquí.
    for name, value in data.model_dump(exclude={"expected_version"}).items():
        setattr(request, name, value)
    return _save(session, request)


def close_request(
    session: Session, actor: UserAccount, request_id: int, data: TravelRequestClose
) -> TravelRequest:
    request = _open(session, request_id, data.expected_version)
    request.status = TravelRequestStatus.CLOSED
    request.close_reason = data.reason
    request.close_note = data.note
    request.closed_at = datetime.now(timezone.utc)
    # La relación y no el id: ya viene cargada con la ficha, y al guardar pisaría el id.
    request.closed_by = actor
    return _save(session, request)


def reopen_request(session: Session, request_id: int, data: TravelRequestReopen) -> TravelRequest:
    request = _current(session, request_id, data.expected_version)
    if request.status != TravelRequestStatus.CLOSED:
        raise TravelRequestNotClosed()
    request.close_reason = None
    request.close_note = None
    request.closed_at = None
    request.closed_by = None
    # Cualquier estado abierto sirve aquí: refresh_status pone el que le corresponde.
    request.status = TravelRequestStatus.NEW
    refresh_status(session, request)
    return _save(session, request)
