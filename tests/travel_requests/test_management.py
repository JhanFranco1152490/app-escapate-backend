from datetime import date, timedelta

import pytest

from app.common.errors import InvalidFields, StaleVersion
from app.travel_requests.errors import TravelRequestClosed, TravelRequestNotClosed
from app.travel_requests.schemas import (
    TravelRequestClose,
    TravelRequestCreate,
    TravelRequestReopen,
    TravelRequestUpdate,
)
from app.travel_requests.services import request_management
from tests.factories import ClientFactory, TravelRequestFactory, UserAccountFactory

TODAY = date(2026, 11, 13)
NEXT_MONTH = TODAY + timedelta(days=35)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(request_management, "today", lambda: TODAY)


@pytest.fixture
def advisor(session, advisor_role):
    return UserAccountFactory(role=advisor_role)


@pytest.fixture
def client(session):
    return ClientFactory()


def exact(client, advisor, **changes) -> dict:
    return {
        "client_id": client.id,
        "destination": "San Andrés",
        "date_mode": "exact",
        "departure_date": NEXT_MONTH,
        "adults": 2,
        "minors": 1,
        "assigned_to_id": advisor.id,
        **changes,
    }


def flexible(client, advisor, **changes) -> dict:
    data = exact(client, advisor, date_mode="flexible", departure_date=None)
    return {
        **data,
        "window_start": date(2026, 12, 1),
        "window_end": date(2026, 12, 31),
        "approx_nights": 5,
        **changes,
    }


def create(session, actor, data: dict):
    return request_management.create_request(session, actor, TravelRequestCreate(**data))


def update(session, request, data: dict, version: int | None = None):
    payload = TravelRequestUpdate(**data, expected_version=version or request.version)
    return request_management.update_request(session, request.id, payload)


def body_of(request) -> dict:
    """Los datos editables de una solicitud guardada, como los enviaría el formulario."""
    return {
        "client_id": request.client_id,
        "destination": request.destination,
        "date_mode": request.date_mode,
        "departure_date": request.departure_date,
        "return_date": request.return_date,
        "window_start": request.window_start,
        "window_end": request.window_end,
        "approx_nights": request.approx_nights,
        "adults": request.adults,
        "minors": request.minors,
        "assigned_to_id": request.assigned_to_id,
    }


def field_errors(error: pytest.ExceptionInfo) -> dict[str, list[str]]:
    return error.value.fields


def test_a_request_with_exact_dates_is_created_new_and_tied_to_its_client(
    session, client, advisor
):
    actor = UserAccountFactory()
    request = create(
        session,
        actor,
        exact(
            client,
            advisor,
            trip_types=["family"],
            budget_min=6_000_000,
            notes="Habitación conectada.\nSin escalas nocturnas.",
        ),
    )

    assert request.status == "new"
    assert request.client.id == client.id
    assert request.created_by.id == actor.id
    assert request.assigned_to.id == advisor.id
    assert request.trip_types == ["family"]
    assert request.notes == "Habitación conectada.\nSin escalas nocturnas."
    assert request.version == 1


def test_a_request_with_a_flexible_period_is_created(session, client, advisor):
    request = create(session, advisor, flexible(client, advisor))

    assert request.date_mode == "flexible"
    assert request.departure_date is None
    assert request.approx_nights == 5


def test_two_identical_requests_are_two_independent_processes(session, client, advisor):
    first = create(session, advisor, exact(client, advisor))
    second = create(session, advisor, exact(client, advisor))

    assert first.id != second.id


def test_an_unknown_client_and_an_ineligible_advisor_are_reported_together(
    session, operations_role
):
    viewer = UserAccountFactory(role=operations_role)
    data = {**exact(ClientFactory(), viewer), "client_id": 999_999_999}

    with pytest.raises(InvalidFields) as error:
        create(session, viewer, data)

    assert field_errors(error) == {
        "client_id": ["El cliente no existe."],
        "assigned_to_id": ["Elige un asesor activo que pueda gestionar solicitudes."],
    }


def test_an_inactive_advisor_cannot_be_responsible(session, client, advisor_role):
    inactive = UserAccountFactory(role=advisor_role, is_active=False)

    with pytest.raises(InvalidFields) as error:
        create(session, inactive, exact(client, inactive))

    assert set(field_errors(error)) == {"assigned_to_id"}


@pytest.mark.parametrize(
    "build, field",
    [
        (lambda c, a: exact(c, a, departure_date=TODAY - timedelta(days=1)), "departure_date"),
        (
            lambda c, a: flexible(
                c, a, window_start=date(2026, 11, 1), window_end=date(2026, 11, 12)
            ),
            "window_end",
        ),
    ],
    ids=["departure", "window-end"],
)
def test_a_new_request_cannot_be_for_a_trip_that_already_passed(
    session, client, advisor, build, field
):
    with pytest.raises(InvalidFields) as error:
        create(session, advisor, build(client, advisor))

    assert field_errors(error) == {field: ["La fecha ya pasó."]}


def test_a_trip_that_starts_today_or_a_period_still_open_is_accepted(session, client, advisor):
    today_trip = create(session, advisor, exact(client, advisor, departure_date=TODAY))
    open_period = create(
        session,
        advisor,
        flexible(client, advisor, window_start=date(2026, 11, 1), window_end=TODAY),
    )

    assert today_trip.departure_date == TODAY
    assert open_period.window_end == TODAY


def test_an_update_keeps_the_changes_and_not_the_status(session, advisor_role):
    request = TravelRequestFactory(
        status="quoting", assigned_to=UserAccountFactory(role=advisor_role)
    )
    other = UserAccountFactory(role=advisor_role)

    updated = update(
        session,
        request,
        {
            **body_of(request),
            "destination": "Santa Marta",
            "assigned_to_id": other.id,
            "minors": 2,
        },
    )

    assert updated.destination == "Santa Marta"
    assert updated.assigned_to.id == other.id
    assert updated.minors == 2
    assert updated.status == "quoting"
    assert updated.version == 2


def test_an_update_can_switch_to_a_flexible_period(session, advisor_role):
    request = TravelRequestFactory(assigned_to=UserAccountFactory(role=advisor_role))
    body = {
        **body_of(request),
        "date_mode": "flexible",
        "departure_date": None,
        "window_start": NEXT_MONTH,
        "window_end": NEXT_MONTH + timedelta(days=20),
    }

    updated = update(session, request, body)

    assert updated.date_mode == "flexible"
    assert updated.departure_date is None


def test_the_client_of_a_request_cannot_change(session, advisor_role):
    request = TravelRequestFactory(assigned_to=UserAccountFactory(role=advisor_role))

    with pytest.raises(InvalidFields) as error:
        update(session, request, {**body_of(request), "client_id": ClientFactory().id})

    assert field_errors(error) == {
        "client_id": ["El cliente de la solicitud no se puede cambiar."]
    }


def test_an_update_over_an_old_version_is_rejected(session, advisor_role):
    request = TravelRequestFactory(assigned_to=UserAccountFactory(role=advisor_role))
    request.destination = "Otro destino"
    session.flush()

    with pytest.raises(StaleVersion):
        update(session, request, body_of(request), version=1)


def test_a_closed_request_cannot_be_edited(session, advisor_role):
    request = TravelRequestFactory(closed=True, assigned_to=UserAccountFactory(role=advisor_role))

    with pytest.raises(TravelRequestClosed):
        update(session, request, body_of(request))


def test_a_past_date_that_did_not_change_is_kept(session, advisor_role):
    started = TravelRequestFactory(
        departure_date=TODAY - timedelta(days=2),
        assigned_to=UserAccountFactory(role=advisor_role),
    )

    updated = update(session, started, {**body_of(started), "minors": 3})

    assert updated.minors == 3


def test_a_date_moved_into_the_past_is_rejected(session, advisor_role):
    request = TravelRequestFactory(assigned_to=UserAccountFactory(role=advisor_role))

    with pytest.raises(InvalidFields) as error:
        update(session, request, {**body_of(request), "departure_date": TODAY - timedelta(days=1)})

    assert field_errors(error) == {"departure_date": ["La fecha ya pasó."]}


def test_editing_one_request_of_a_client_leaves_the_other_alone(session, advisor_role):
    advisor = UserAccountFactory(role=advisor_role)
    first = TravelRequestFactory(assigned_to=advisor, destination="San Andrés")
    second = TravelRequestFactory(client=first.client, assigned_to=advisor, destination="Cancún")

    update(session, first, {**body_of(first), "destination": "Cartagena"})
    session.refresh(second)

    assert second.destination == "Cancún"
    assert second.version == 1


@pytest.mark.parametrize(
    "reason", ["client_declined", "no_response", "bought_elsewhere", "duplicate", "other"]
)
def test_a_request_is_closed_with_its_reason_who_and_when(session, reason):
    request = TravelRequestFactory()
    actor = UserAccountFactory()
    note = "Aplazó el viaje." if reason == "other" else None

    closed = request_management.close_request(
        session,
        actor,
        request.id,
        TravelRequestClose(reason=reason, note=note, expected_version=request.version),
    )

    assert closed.status == "closed"
    assert closed.close_reason == reason
    assert closed.close_note == note
    assert closed.closed_by.id == actor.id
    assert closed.closed_at is not None
    assert closed.version == 2


def test_closing_twice_is_rejected(session):
    request = TravelRequestFactory(closed=True)

    with pytest.raises(TravelRequestClosed):
        request_management.close_request(
            session,
            UserAccountFactory(),
            request.id,
            TravelRequestClose(reason="no_response", expected_version=request.version),
        )


def test_closing_over_an_old_version_is_rejected(session):
    request = TravelRequestFactory()

    with pytest.raises(StaleVersion):
        request_management.close_request(
            session,
            UserAccountFactory(),
            request.id,
            TravelRequestClose(reason="no_response", expected_version=request.version + 1),
        )


def test_reopening_clears_the_close_and_goes_back_to_new(session):
    request = TravelRequestFactory(closed=True, close_reason="other", close_note="Aplazado")

    reopened = request_management.reopen_request(
        session, request.id, TravelRequestReopen(expected_version=request.version)
    )

    assert reopened.status == "new"
    assert reopened.close_reason is None
    assert reopened.close_note is None
    assert reopened.closed_by is None
    assert reopened.closed_at is None
    assert reopened.version == 2


def test_reopening_an_open_request_is_rejected(session):
    request = TravelRequestFactory()

    with pytest.raises(TravelRequestNotClosed):
        request_management.reopen_request(
            session, request.id, TravelRequestReopen(expected_version=request.version)
        )


def test_reopening_over_an_old_version_is_rejected(session):
    request = TravelRequestFactory(closed=True)

    with pytest.raises(StaleVersion):
        request_management.reopen_request(
            session, request.id, TravelRequestReopen(expected_version=request.version + 1)
        )
