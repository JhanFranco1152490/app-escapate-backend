from contextlib import contextmanager
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.travel_requests.models import TravelRequest
from tests.factories import TravelRequestFactory


@contextmanager
def _violates(constraint: str):
    # Se compara el nombre que entrega el driver y no el texto del mensaje, que viene en el
    # idioma del servidor de base de datos.
    with pytest.raises(IntegrityError) as error:
        yield
    assert error.value.orig.diag.constraint_name == constraint


def test_a_request_keeps_what_the_client_asked_for(session):
    request = TravelRequestFactory(
        trip_types=["leisure", "family"],
        budget_min=6_000_000,
        budget_max=8_000_000,
        notes="Habitación conectada.\nSin escalas nocturnas.",
    )
    session.expire(request)

    assert request.status == "new"
    assert request.trip_types == ["leisure", "family"]
    assert request.budget_max == 8_000_000
    assert request.notes == "Habitación conectada.\nSin escalas nocturnas."
    assert request.client is not None
    assert request.assigned_to is not None


def test_a_request_with_a_flexible_period_has_no_exact_dates(session):
    request = TravelRequestFactory(flexible=True)

    assert request.departure_date is None
    assert request.window_start <= request.window_end


def test_trip_types_default_to_an_empty_list_in_the_database(session):
    session.execute(
        text(
            "INSERT INTO travel_request (client_id, destination, date_mode, departure_date, "
            "adults, minors, status, assigned_to_id, created_by_id, version) "
            "SELECT client_id, destination, date_mode, departure_date, adults, minors, status, "
            "assigned_to_id, created_by_id, 1 FROM travel_request WHERE id = :id"
        ),
        {"id": TravelRequestFactory().id},
    )

    stored = session.execute(
        text("SELECT trip_types FROM travel_request ORDER BY id DESC LIMIT 1")
    ).scalar_one()
    assert stored == []


def test_a_closed_request_keeps_who_closed_it_and_why(session):
    request = TravelRequestFactory(closed=True)

    assert request.status == "closed"
    assert request.close_reason == "client_declined"
    assert request.closed_by is not None
    assert request.closed_at is not None


@pytest.mark.parametrize(
    "request_id, code", [(1, "SOL-0001"), (231, "SOL-0231"), (12345, "SOL-12345")]
)
def test_the_code_comes_from_the_id(request_id, code):
    assert TravelRequest(id=request_id).code == code


def test_a_new_request_starts_at_version_one_and_each_change_adds_one(session):
    request = TravelRequestFactory()
    assert request.version == 1

    request.destination = "Santa Marta"
    session.flush()

    assert request.version == 2


def test_saving_over_a_version_someone_else_already_changed_fails(session):
    request = TravelRequestFactory()
    session.execute(
        text("UPDATE travel_request SET version = version + 1 WHERE id = :id"),
        {"id": request.id},
    )

    request.destination = "Santa Marta"
    with pytest.raises(StaleDataError):
        session.flush()


_DAY = date(2026, 12, 18)
_NOW = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "overrides, constraint",
    [
        pytest.param({"date_mode": "someday"}, "ck_travel_request_date_mode", id="unknown-mode"),
        pytest.param(
            {"departure_date": None}, "ck_travel_request_exact_dates", id="exact-no-departure"
        ),
        pytest.param(
            {"departure_date": _DAY, "return_date": date(2026, 12, 17)},
            "ck_travel_request_exact_dates",
            id="return-before-departure",
        ),
        pytest.param(
            {"window_start": _DAY, "window_end": _DAY},
            "ck_travel_request_exact_dates",
            id="exact-with-window",
        ),
        pytest.param({"approx_nights": 5}, "ck_travel_request_exact_dates", id="exact-nights"),
        pytest.param(
            {"flexible": True, "departure_date": _DAY},
            "ck_travel_request_flexible_dates",
            id="flexible-with-departure",
        ),
        pytest.param(
            {"flexible": True, "window_end": None},
            "ck_travel_request_flexible_dates",
            id="flexible-without-end",
        ),
        pytest.param(
            {"flexible": True, "window_start": date(2026, 12, 31), "window_end": _DAY},
            "ck_travel_request_flexible_dates",
            id="window-backwards",
        ),
        pytest.param(
            {"flexible": True, "approx_nights": 0},
            "ck_travel_request_approx_nights",
            id="zero-nights",
        ),
        pytest.param({"adults": 0}, "ck_travel_request_adults", id="no-adults"),
        pytest.param({"adults": 100}, "ck_travel_request_adults", id="too-many-adults"),
        pytest.param({"minors": -1}, "ck_travel_request_minors", id="negative-minors"),
        pytest.param({"budget_min": 0}, "ck_travel_request_budget", id="zero-budget"),
        pytest.param(
            {"budget_min": 8_000_000, "budget_max": 6_000_000},
            "ck_travel_request_budget",
            id="budget-backwards",
        ),
        pytest.param(
            {"trip_types": ["family", "spa"]},
            "ck_travel_request_trip_types",
            id="unknown-trip-type",
        ),
        pytest.param(
            {"accommodation_category": "seven_star"},
            "ck_travel_request_accommodation_category",
            id="unknown-accommodation",
        ),
        pytest.param({"status": "won"}, "ck_travel_request_status", id="unknown-status"),
        pytest.param({"status": "closed"}, "ck_travel_request_closed", id="closed-no-reason"),
        pytest.param(
            {"close_reason": "no_response", "closed_at": _NOW},
            "ck_travel_request_closed",
            id="open-with-reason",
        ),
        pytest.param(
            {"closed": True, "close_reason": "lost"},
            "ck_travel_request_close_reason",
            id="unknown-close-reason",
        ),
        pytest.param(
            {"closed": True, "close_reason": "other", "close_note": None},
            "ck_travel_request_close_note",
            id="other-without-note",
        ),
    ],
)
def test_the_database_rejects_an_inconsistent_request(session, overrides, constraint):
    with _violates(constraint):
        TravelRequestFactory(**overrides)


def test_a_budget_with_only_one_end_is_accepted(session):
    only_min = TravelRequestFactory(budget_min=5_000_000)
    only_max = TravelRequestFactory(budget_max=9_000_000)

    assert only_min.id is not None
    assert only_max.id is not None


def test_two_identical_requests_of_the_same_client_are_two_requests(session):
    first = TravelRequestFactory()
    second = TravelRequestFactory(
        client=first.client,
        destination=first.destination,
        departure_date=first.departure_date,
    )

    assert first.id != second.id
