"""Carga de los viajeros de las solicitudes de demostración. Va en un paso propio, después de
las solicitudes, para que también llegue a una base donde ya estaban sembradas. Repetible:
una solicitud que ya tiene viajeros se omite, y también una que alguien cerró a mano.

En el entorno compartido otras personas registran solicitudes: si hay varias del mismo cliente
al mismo destino, se usa la más antigua, que es la que creó la carga.

Los viajeros se asocian con el servicio de la aplicación, para respetar sus reglas.
"""

from functools import partial

from sqlalchemy import exists
from sqlmodel import Session, col, select

from app.accounts.models import UserAccount
from app.clients.models import Client, Traveler
from app.common.seeding import SeededRecord, same_document, seed_if_new
from app.travel_requests.demo_data import DEMO_REQUEST_TRAVELERS, DemoRequestTravelers
from app.travel_requests.models import (
    TravelRequest,
    TravelRequestStatus,
    TravelRequestTraveler,
)
from app.travel_requests.schemas import RequestTravelersAdd
from app.travel_requests.services.request_travelers import add_travelers


def _associate(
    session: Session, actor: UserAccount, request: TravelRequest, demo: DemoRequestTravelers
) -> None:
    ids = [
        session.exec(select(Traveler.id).where(same_document(Traveler, *document))).one()
        for document in demo.traveler_documents
    ]
    add_travelers(session, actor, request.id, RequestTravelersAdd(traveler_ids=ids))


def seed_demo_request_travelers(session: Session, actor: UserAccount) -> list[SeededRecord]:
    records = []
    for demo in DEMO_REQUEST_TRAVELERS:
        client = session.exec(
            select(Client).where(same_document(Client, *demo.client_document))
        ).one()
        request = session.exec(
            select(TravelRequest)
            .where(
                TravelRequest.client_id == client.id,
                TravelRequest.destination == demo.destination,
            )
            .order_by(col(TravelRequest.id))
        ).first()
        has_travelers = exists().where(TravelRequestTraveler.travel_request_id == TravelRequest.id)
        already_done = has_travelers | (TravelRequest.status == TravelRequestStatus.CLOSED)
        records.append(
            seed_if_new(
                session,
                TravelRequest,
                "Viajeros de la solicitud",
                f"{demo.destination} ({client.display_name})",
                (TravelRequest.id == request.id) & already_done,
                partial(_associate, session, actor, request, demo),
            )
        )
    return records
