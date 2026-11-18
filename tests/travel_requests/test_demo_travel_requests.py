from sqlmodel import select

from app.accounts.services.demo_accounts import seed_demo_accounts
from app.clients.services.demo_clients import seed_demo_clients
from app.common.dates import today
from app.travel_requests.demo_data import DEMO_TRAVEL_REQUESTS
from app.travel_requests.models import TravelRequest
from app.travel_requests.services.demo_travel_requests import seed_demo_travel_requests


def _seed(session):
    accounts = seed_demo_accounts(session)
    actor = accounts[0].user
    seed_demo_clients(session, actor)
    return actor, seed_demo_travel_requests(session, actor)


def test_it_loads_open_and_closed_requests_of_the_demo_clients(session):
    actor, records = _seed(session)

    requests = session.exec(select(TravelRequest)).all()
    assert len(requests) == len(DEMO_TRAVEL_REQUESTS)
    assert all(record.created for record in records)
    assert {request.date_mode for request in requests} == {"exact", "flexible"}
    assert {request.status for request in requests} == {"new", "closed"}
    assert all(request.created_by_id == actor.id for request in requests)


def test_the_requests_belong_to_two_advisors_and_are_future_trips(session):
    _seed(session)

    requests = session.exec(select(TravelRequest)).all()

    assert len({request.assigned_to_id for request in requests}) == 2
    assert all((request.departure_date or request.window_end) > today() for request in requests)


def test_loading_it_again_skips_every_request(session):
    actor, _ = _seed(session)

    records = seed_demo_travel_requests(session, actor)

    assert not any(record.created for record in records)
    assert len(session.exec(select(TravelRequest)).all()) == len(DEMO_TRAVEL_REQUESTS)
    assert records[0].label == "San Andrés (Cliente Demostración)"
