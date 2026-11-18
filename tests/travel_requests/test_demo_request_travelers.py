from sqlmodel import select

from app.accounts.services.demo_accounts import seed_demo_accounts
from app.clients.services.demo_clients import seed_demo_clients
from app.travel_requests.demo_data import DEMO_REQUEST_TRAVELERS
from app.travel_requests.models import TravelRequest, TravelRequestTraveler
from app.travel_requests.services.demo_request_travelers import seed_demo_request_travelers
from app.travel_requests.services.demo_travel_requests import seed_demo_travel_requests
from app.travel_requests.services.request_travelers import list_travelers


def _seed_requests(session):
    """Lo que ya había antes de los viajeros de la solicitud: cuentas, clientes y
    solicitudes."""
    actor = seed_demo_accounts(session)[0].user
    seed_demo_clients(session, actor)
    seed_demo_travel_requests(session, actor)
    return actor


def _counts(session, destination: str) -> tuple[int, int, int, int]:
    """(adultos pedidos, menores pedidos, adultos asociados, menores asociados)."""
    request = session.exec(
        select(TravelRequest).where(TravelRequest.destination == destination)
    ).one()
    travelers = list_travelers(session, request.id)
    minors = sum(traveler.is_minor for traveler in travelers)
    return request.adults, request.minors, len(travelers) - minors, minors


def test_it_associates_the_demo_travelers_to_open_requests(session):
    actor = _seed_requests(session)

    records = seed_demo_request_travelers(session, actor)

    assert all(record.created for record in records)
    links = session.exec(select(TravelRequestTraveler)).all()
    assert len(links) == sum(len(demo.traveler_documents) for demo in DEMO_REQUEST_TRAVELERS)
    assert all(link.added_by_id == actor.id for link in links)


def test_each_request_shows_a_different_count_notice(session):
    actor = _seed_requests(session)
    seed_demo_request_travelers(session, actor)

    # Coinciden; sobra un menor y falta un adulto; faltan adultos.
    assert _counts(session, "San Andrés") == (2, 1, 2, 1)
    assert _counts(session, "Cartagena y Santa Marta") == (2, 0, 1, 1)
    assert _counts(session, "Medellín") == (6, 0, 1, 0)


def test_requests_without_demo_travelers_stay_empty(session):
    actor = _seed_requests(session)
    seed_demo_request_travelers(session, actor)

    for destination in ("Eje Cafetero", "Cancún"):
        request = session.exec(
            select(TravelRequest).where(TravelRequest.destination == destination)
        ).one()
        assert list_travelers(session, request.id) == []


def test_the_titular_is_shown_as_the_client(session):
    actor = _seed_requests(session)
    seed_demo_request_travelers(session, actor)

    request = session.exec(
        select(TravelRequest).where(TravelRequest.destination == "San Andrés")
    ).one()
    titular = [t for t in list_travelers(session, request.id) if t.is_the_client]
    assert [t.document_number for t in titular] == ["1000000101"]


def test_loading_it_again_skips_every_request(session):
    actor = _seed_requests(session)
    seed_demo_request_travelers(session, actor)

    records = seed_demo_request_travelers(session, actor)

    assert not any(record.created for record in records)
    assert len(session.exec(select(TravelRequestTraveler)).all()) == sum(
        len(demo.traveler_documents) for demo in DEMO_REQUEST_TRAVELERS
    )
    assert (records[0].kind, records[0].label) == (
        "Viajeros de la solicitud",
        "San Andrés (Cliente Demostración)",
    )
