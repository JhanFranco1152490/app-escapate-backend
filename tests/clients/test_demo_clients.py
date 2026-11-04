from sqlmodel import select

from app.clients.demo_data import DEMO_CLIENTS, DEMO_TRAVELERS
from app.clients.models import Client, ClientType, Traveler
from app.clients.services.demo_clients import seed_demo_clients
from tests.factories import UserAccountFactory


def test_it_loads_a_person_a_company_and_their_travelers(session):
    actor = UserAccountFactory()

    records = seed_demo_clients(session, actor)

    clients = session.exec(select(Client)).all()
    assert {client.client_type for client in clients} == {ClientType.PERSON, ClientType.COMPANY}
    assert len(clients) == len(DEMO_CLIENTS)
    assert len(session.exec(select(Traveler)).all()) == len(DEMO_TRAVELERS)
    assert all(record.created for record in records)
    assert all(client.created_by_id == actor.id for client in clients)


def test_a_traveler_can_be_the_same_person_as_a_demo_client(session):
    seed_demo_clients(session, UserAccountFactory())

    travelers = session.exec(select(Traveler)).all()

    assert any(traveler.is_the_client for traveler in travelers)
    assert any(traveler.is_minor for traveler in travelers)


def test_loading_it_again_skips_every_record(session):
    actor = UserAccountFactory()
    seed_demo_clients(session, actor)

    records = seed_demo_clients(session, actor)

    assert not any(record.created for record in records)
    assert len(session.exec(select(Client)).all()) == len(DEMO_CLIENTS)
    assert len(session.exec(select(Traveler)).all()) == len(DEMO_TRAVELERS)


def test_it_only_uses_invented_contact_data(session):
    seed_demo_clients(session, UserAccountFactory())

    emails = [client.email for client in session.exec(select(Client)).all() if client.email]

    assert emails
    assert all(email.endswith("@example.com") for email in emails)
