"""Carga de clientes y viajeros de demostración. Repetible: un documento ya registrado se
omite."""

from functools import partial

from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.clients.demo_data import (
    DEMO_CLIENTS,
    DEMO_REFERENCE_DOCUMENT,
    DEMO_TRAVELERS,
    DemoTraveler,
)
from app.clients.models import Client, Traveler
from app.clients.schemas import ClientCreate, TravelerCreate
from app.clients.services.client_management import create_client
from app.clients.services.traveler_management import create_traveler
from app.common.seeding import SeededRecord, seed_if_new


def _reference_client_id(session: Session) -> int:
    document_type, document_number = DEMO_REFERENCE_DOCUMENT
    return session.exec(
        select(Client.id).where(
            Client.document_type == document_type, Client.document_number == document_number
        )
    ).one()


def _create_traveler(session: Session, actor: UserAccount, traveler: DemoTraveler) -> None:
    fields = traveler.fields
    if traveler.has_reference_client:
        fields = fields | {"reference_client_id": _reference_client_id(session)}
    create_traveler(session, actor, TravelerCreate(**fields, data_consent=True))


def seed_demo_clients(session: Session, actor: UserAccount) -> list[SeededRecord]:
    records = [
        seed_if_new(
            session,
            Client,
            "Cliente",
            data["document_type"],
            data["document_number"],
            partial(create_client, session, actor, ClientCreate(**data, data_consent=True)),
        )
        for data in DEMO_CLIENTS
    ]
    # Después de los clientes: algunos viajeros tienen a la persona de demostración de referencia.
    records += [
        seed_if_new(
            session,
            Traveler,
            "Viajero",
            traveler.fields["document_type"],
            traveler.fields["document_number"],
            partial(_create_traveler, session, actor, traveler),
        )
        for traveler in DEMO_TRAVELERS
    ]
    return records
