"""Quién viaja en una solicitud: listar, asociar y quitar viajeros ya registrados.

Asociar y quitar no editan la solicitud (ni su versión ni su fecha de modificación): quien
tiene sus datos abiertos en otra pestaña no recibe un conflicto por esto. Las dos operaciones
son idempotentes, porque dos asesores pueden hacer lo mismo a la vez.
"""

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.accounts.models import UserAccount
from app.clients.models import Traveler
from app.common.errors import InvalidFields, NotFound
from app.common.schemas import UserRef
from app.travel_requests.errors import UNKNOWN_TRAVELER
from app.travel_requests.models import TravelRequest, TravelRequestTraveler
from app.travel_requests.schemas import RequestTraveler, RequestTravelersAdd
from app.travel_requests.services.request_management import ensure_open


def _request(session: Session, request_id: int) -> TravelRequest:
    request = session.get(TravelRequest, request_id)
    if request is None:
        raise NotFound()
    return request


def _open_for_travelers(session: Session, request_id: int) -> TravelRequest:
    # FOR SHARE: un cierre simultáneo espera a que esta transacción termine, o esta ve la
    # solicitud ya cerrada. Así nunca queda un viajero agregado a una solicitud que se cerró
    # antes. Dos asociaciones a la vez no se bloquean entre sí.
    request = session.exec(
        select(TravelRequest)
        .where(TravelRequest.id == request_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if request is None:
        raise NotFound()
    ensure_open(request)
    return request


def _item(link: TravelRequestTraveler, client_id: int) -> RequestTraveler:
    traveler = link.traveler
    return RequestTraveler(
        id=traveler.id,
        first_name=traveler.first_name,
        last_name=traveler.last_name,
        full_name=traveler.full_name,
        document_type=traveler.document_type,
        document_number=traveler.document_number,
        age=traveler.age,
        is_minor=traveler.is_minor,
        is_the_client=traveler.is_the_client and traveler.reference_client_id == client_id,
        added_at=link.added_at,
        added_by=UserRef.model_validate(link.added_by),
    )


def list_travelers(session: Session, request_id: int) -> list[RequestTraveler]:
    request = _request(session, request_id)
    links = session.exec(
        select(TravelRequestTraveler)
        .where(TravelRequestTraveler.travel_request_id == request_id)
        .options(
            joinedload(TravelRequestTraveler.traveler),
            joinedload(TravelRequestTraveler.added_by),
        )
        .order_by(col(TravelRequestTraveler.added_at), col(TravelRequestTraveler.traveler_id))
    ).all()
    return [_item(link, request.client_id) for link in links]


def add_travelers(
    session: Session, actor: UserAccount, request_id: int, data: RequestTravelersAdd
) -> list[RequestTraveler]:
    _open_for_travelers(session, request_id)
    found = session.exec(select(func.count()).where(col(Traveler.id).in_(data.traveler_ids))).one()
    if found != len(data.traveler_ids):
        raise InvalidFields(fields={"traveler_ids": [UNKNOWN_TRAVELER]})

    rows = [
        {"travel_request_id": request_id, "traveler_id": traveler_id, "added_by_id": actor.id}
        for traveler_id in data.traveler_ids
    ]
    session.exec(insert(TravelRequestTraveler).values(rows).on_conflict_do_nothing())
    session.commit()
    return list_travelers(session, request_id)


def remove_traveler(session: Session, request_id: int, traveler_id: int) -> None:
    _open_for_travelers(session, request_id)
    session.exec(
        delete(TravelRequestTraveler).where(
            col(TravelRequestTraveler.travel_request_id) == request_id,
            col(TravelRequestTraveler.traveler_id) == traveler_id,
        )
    )
    session.commit()
