from datetime import date, datetime, timedelta, timezone

import pytest
from sqlmodel import select

from app.clients.models import Traveler
from app.common.errors import InvalidFields, NotFound
from app.travel_requests.errors import TravelRequestClosed
from app.travel_requests.models import TravelRequestTraveler
from app.travel_requests.schemas import RequestTravelersAdd, TravelRequestReopen
from app.travel_requests.services import request_management, request_travelers
from tests.factories import (
    ClientFactory,
    TravelerFactory,
    TravelRequestFactory,
    TravelRequestTravelerFactory,
    UserAccountFactory,
)

MISSING_ID = 2**62


@pytest.fixture
def actor(session):
    return UserAccountFactory()


def add(session, actor, request, *travelers):
    return request_travelers.add_travelers(
        session,
        actor,
        request.id,
        RequestTravelersAdd(traveler_ids=[traveler.id for traveler in travelers]),
    )


def associated_ids(session, request) -> list[int]:
    return [item.id for item in request_travelers.list_travelers(session, request.id)]


def test_one_traveler_is_associated(session, actor):
    request, traveler = TravelRequestFactory(), TravelerFactory()

    result = add(session, actor, request, traveler)

    assert [item.id for item in result] == [traveler.id]
    assert result[0].added_by.id == actor.id
    assert result[0].added_at is not None


def test_several_travelers_are_associated_at_once(session, actor):
    request = TravelRequestFactory()
    travelers = [TravelerFactory() for _ in range(3)]

    add(session, actor, request, *travelers)

    assert sorted(associated_ids(session, request)) == sorted(t.id for t in travelers)


def test_associating_a_traveler_twice_neither_fails_nor_repeats_it(session, actor):
    request, traveler, other = TravelRequestFactory(), TravelerFactory(), TravelerFactory()
    add(session, actor, request, traveler)

    result = add(session, actor, request, traveler, other)

    assert sorted(item.id for item in result) == sorted([traveler.id, other.id])


def test_an_unknown_traveler_rejects_the_whole_list(session, actor):
    request, traveler = TravelRequestFactory(), TravelerFactory()
    data = RequestTravelersAdd(traveler_ids=[traveler.id, MISSING_ID])

    with pytest.raises(InvalidFields) as error:
        request_travelers.add_travelers(session, actor, request.id, data)

    assert error.value.fields == {"traveler_ids": ["Uno de los viajeros no existe."]}
    assert associated_ids(session, request) == []


def test_an_unknown_request_is_not_found(session, actor):
    data = RequestTravelersAdd(traveler_ids=[TravelerFactory().id])

    with pytest.raises(NotFound):
        request_travelers.add_travelers(session, actor, MISSING_ID, data)
    with pytest.raises(NotFound):
        request_travelers.list_travelers(session, MISSING_ID)
    with pytest.raises(NotFound):
        request_travelers.remove_traveler(session, MISSING_ID, 1)


def test_a_closed_request_does_not_change_its_travelers(session, actor):
    link = TravelRequestTravelerFactory(travel_request=TravelRequestFactory(closed=True))

    with pytest.raises(TravelRequestClosed):
        add(session, actor, link.travel_request, TravelerFactory())
    with pytest.raises(TravelRequestClosed):
        request_travelers.remove_traveler(session, link.travel_request_id, link.traveler_id)
    assert associated_ids(session, link.travel_request) == [link.traveler_id]


def test_travelers_are_listed_in_the_order_they_were_associated(session):
    request = TravelRequestFactory()
    # Los id van al revés del orden de asociación, para que el orden salga de la hora.
    late, early = TravelerFactory(), TravelerFactory()
    morning = datetime(2026, 11, 18, 9, tzinfo=timezone.utc)
    TravelRequestTravelerFactory(
        travel_request=request, traveler=late, added_at=morning + timedelta(hours=2)
    )
    TravelRequestTravelerFactory(travel_request=request, traveler=early, added_at=morning)

    assert associated_ids(session, request) == [early.id, late.id]


def test_travelers_associated_at_once_are_listed_by_id(session, actor):
    request = TravelRequestFactory()
    first, second = TravelerFactory(), TravelerFactory()

    add(session, actor, request, second, first)

    assert associated_ids(session, request) == [first.id, second.id]


def test_each_traveler_keeps_their_own_information(session, actor):
    request = TravelRequestFactory()
    adult = TravelerFactory(first_name="Marcela", birth_date=date(1988, 4, 2))
    minor = TravelerFactory(first_name="Camila", document_type="TI", birth_date=date(2012, 6, 9))
    add(session, actor, request, adult, minor)

    by_id = {item.id: item for item in request_travelers.list_travelers(session, request.id)}

    assert by_id[adult.id].first_name == "Marcela"
    assert by_id[adult.id].is_minor is False
    assert by_id[minor.id].document_type == "TI"
    assert by_id[minor.id].document_number == minor.document_number
    assert by_id[minor.id].is_minor is True
    assert by_id[minor.id].age == minor.age


def test_is_the_client_only_for_the_client_of_this_request(session, actor):
    client = ClientFactory()
    traveler = TravelerFactory(reference_client=client, is_the_client=True)
    own = TravelRequestFactory(client=client)
    other = TravelRequestFactory()
    add(session, actor, own, traveler)
    add(session, actor, other, traveler)

    assert request_travelers.list_travelers(session, own.id)[0].is_the_client is True
    assert request_travelers.list_travelers(session, other.id)[0].is_the_client is False


def test_removing_a_traveler_keeps_their_data(session, actor):
    link = TravelRequestTravelerFactory()
    request, traveler_id, name = link.travel_request, link.traveler_id, link.traveler.full_name

    request_travelers.remove_traveler(session, request.id, traveler_id)

    assert associated_ids(session, request) == []
    session.expire_all()
    assert session.get(Traveler, traveler_id).full_name == name


def test_removing_a_traveler_that_was_not_associated_does_not_fail(session):
    request = TravelRequestFactory()

    request_travelers.remove_traveler(session, request.id, TravelerFactory().id)

    assert associated_ids(session, request) == []


def test_the_same_traveler_in_two_requests_is_removed_from_one_only(session, actor):
    traveler = TravelerFactory()
    first, second = TravelRequestFactory(), TravelRequestFactory()
    add(session, actor, first, traveler)
    add(session, actor, second, traveler)

    request_travelers.remove_traveler(session, first.id, traveler.id)

    assert associated_ids(session, first) == []
    assert associated_ids(session, second) == [traveler.id]


def test_associating_and_removing_do_not_change_the_request(session, actor):
    request, traveler = TravelRequestFactory(), TravelerFactory()
    session.flush()
    session.refresh(request)
    version, updated_at = request.version, request.updated_at

    add(session, actor, request, traveler)
    request_travelers.remove_traveler(session, request.id, traveler.id)

    session.refresh(request)
    assert (request.version, request.updated_at) == (version, updated_at)


def test_reopening_a_request_keeps_its_travelers(session, actor):
    request = TravelRequestFactory(closed=True)
    link = TravelRequestTravelerFactory(travel_request=request)
    session.flush()
    session.refresh(request)

    request_management.reopen_request(
        session, request.id, TravelRequestReopen(expected_version=request.version)
    )

    rows = session.exec(
        select(TravelRequestTraveler).where(TravelRequestTraveler.travel_request_id == request.id)
    ).all()
    assert [row.traveler_id for row in rows] == [link.traveler_id]
