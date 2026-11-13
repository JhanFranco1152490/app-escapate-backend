"""Carga de solicitudes de viaje de demostración. Repetible: una solicitud del mismo cliente
al mismo destino se omite.

Va después de los clientes de demostración: se buscan por su documento. Las solicitudes
cerradas se cierran con el servicio de cierre, para respetar sus reglas.
"""

from datetime import timedelta
from functools import partial

from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.clients.models import Client
from app.common.dates import today
from app.common.seeding import SeededRecord, same_document, seed_if_new
from app.travel_requests.demo_data import DEMO_TRAVEL_REQUESTS, DemoTravelRequest
from app.travel_requests.models import TravelRequest
from app.travel_requests.schemas import TravelRequestClose, TravelRequestCreate
from app.travel_requests.services.request_management import close_request, create_request


def _find(session: Session, model: type, document: tuple[str, str]):
    return session.exec(select(model).where(same_document(model, *document))).one()


def _create(session: Session, actor: UserAccount, demo: DemoTravelRequest, client: Client) -> None:
    advisor = actor
    if demo.advisor_document is not None:
        advisor = _find(session, UserAccount, demo.advisor_document)
    dates = {name: today() + timedelta(days=days) for name, days in demo.days_from_today.items()}
    request = create_request(
        session,
        actor,
        TravelRequestCreate(
            client_id=client.id,
            destination=demo.destination,
            assigned_to_id=advisor.id,
            **dates,
            **demo.fields,
        ),
    )
    if demo.close_reason is not None:
        close_request(
            session,
            actor,
            request.id,
            TravelRequestClose(reason=demo.close_reason, expected_version=request.version),
        )


def seed_demo_travel_requests(session: Session, actor: UserAccount) -> list[SeededRecord]:
    records = []
    for demo in DEMO_TRAVEL_REQUESTS:
        client = _find(session, Client, demo.client_document)
        records.append(
            seed_if_new(
                session,
                TravelRequest,
                "Solicitud",
                f"{demo.destination} ({client.display_name})",
                (TravelRequest.client_id == client.id)
                & (TravelRequest.destination == demo.destination),
                partial(_create, session, actor, demo, client),
            )
        )
    return records
