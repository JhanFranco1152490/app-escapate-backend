from app.travel_requests.services.request_status import refresh_status
from tests.factories import TravelRequestFactory


def test_an_open_request_without_drafts_or_quotes_is_new(session):
    request = TravelRequestFactory(status="quoted")

    refresh_status(session, request)

    assert request.status == "new"


def test_a_closed_request_is_left_alone(session):
    request = TravelRequestFactory(closed=True)

    refresh_status(session, request)

    assert request.status == "closed"
