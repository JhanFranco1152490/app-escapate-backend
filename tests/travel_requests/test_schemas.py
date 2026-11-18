from datetime import date

import pytest
from pydantic import ValidationError

from app.travel_requests.schemas import (
    RequestSort,
    StatusFilter,
    TravelRequestClose,
    TravelRequestCreate,
    TravelRequestFilters,
    TravelRequestUpdate,
)

EXACT = {
    "client_id": 1,
    "destination": "San Andrés",
    "date_mode": "exact",
    "departure_date": "2026-12-18",
    "adults": 2,
    "minors": 1,
    "assigned_to_id": 1,
}
FLEXIBLE = {
    **{key: value for key, value in EXACT.items() if key != "departure_date"},
    "date_mode": "flexible",
    "window_start": "2026-12-01",
    "window_end": "2026-12-31",
    "approx_nights": 5,
}


def fields(schema, data: dict) -> dict[str, list[str]]:
    with pytest.raises(ValidationError) as caught:
        schema(**data)
    found: dict[str, list[str]] = {}
    for error in caught.value.errors():
        found.setdefault(".".join(str(part) for part in error["loc"]), []).append(error["msg"])
    return found


def test_a_request_with_exact_dates_is_valid():
    request = TravelRequestCreate(**EXACT, return_date="2026-12-24", origin=" Cúcuta ")

    assert request.departure_date == date(2026, 12, 18)
    assert request.return_date == date(2026, 12, 24)
    assert request.origin == "Cúcuta"
    assert request.trip_types == []
    assert request.notes is None


def test_a_request_with_a_flexible_period_is_valid():
    request = TravelRequestCreate(**FLEXIBLE)

    assert request.window_start == date(2026, 12, 1)
    assert request.approx_nights == 5
    assert request.departure_date is None


def test_the_return_is_optional_and_may_be_the_same_day():
    assert TravelRequestCreate(**EXACT).return_date is None
    assert TravelRequestCreate(**EXACT, return_date="2026-12-18").return_date is not None


def test_missing_required_fields_are_reported_together_each_on_its_field():
    errors = fields(TravelRequestCreate, {"date_mode": "exact", "destination": "  "})

    assert set(errors) == {
        "client_id",
        "destination",
        "departure_date",
        "adults",
        "minors",
        "assigned_to_id",
    }
    assert errors["destination"] == ["Este campo es obligatorio."]
    assert errors["departure_date"] == ["Indica la fecha de salida."]


def test_a_flexible_period_needs_both_ends():
    data = {key: value for key, value in FLEXIBLE.items() if not key.startswith("window_")}

    errors = fields(TravelRequestCreate, {**data, "approx_nights": None})

    assert errors == {
        "window_start": ["Indica desde cuándo."],
        "window_end": ["Indica hasta cuándo."],
    }


def test_fields_of_the_other_date_mode_are_rejected_not_ignored():
    exact = fields(
        TravelRequestCreate,
        {**EXACT, "window_start": "2026-12-01", "window_end": "2026-12-31", "approx_nights": 5},
    )
    flexible = fields(
        TravelRequestCreate,
        {**FLEXIBLE, "departure_date": "2026-12-18", "return_date": "2026-12-24"},
    )

    not_exact = ["No aplica con fechas exactas."]
    not_flexible = ["No aplica con un período flexible."]
    assert exact == {
        "window_start": not_exact,
        "window_end": not_exact,
        "approx_nights": not_exact,
    }
    assert flexible == {"departure_date": not_flexible, "return_date": not_flexible}


def test_dates_cannot_go_backwards():
    exact = fields(TravelRequestCreate, {**EXACT, "return_date": "2026-12-17"})
    flexible = fields(TravelRequestCreate, {**FLEXIBLE, "window_end": "2026-11-30"})

    assert exact == {"return_date": ["No puede ser anterior a la salida."]}
    assert flexible == {"window_end": ["No puede ser anterior al inicio."]}


def test_the_nights_must_fit_in_the_period():
    assert TravelRequestCreate(**{**FLEXIBLE, "approx_nights": 30}).approx_nights == 30
    errors = fields(TravelRequestCreate, {**FLEXIBLE, "approx_nights": 31})

    assert errors == {"approx_nights": ["No caben en el período elegido."]}


@pytest.mark.parametrize("nights", [0, 366])
def test_the_nights_are_between_one_and_a_year(nights):
    assert "approx_nights" in fields(TravelRequestCreate, {**FLEXIBLE, "approx_nights": nights})


def test_an_unknown_date_mode_does_not_also_complain_about_the_dates():
    errors = fields(TravelRequestCreate, {**EXACT, "date_mode": "someday"})

    assert set(errors) == {"date_mode"}


@pytest.mark.parametrize(
    "adults, minors", [(0, 0), (100, 0), (1, -1), (1, 100)], ids=["no-adults", "100", "-1", "100m"]
)
def test_travellers_are_counted_within_limits(adults, minors):
    assert fields(TravelRequestCreate, {**EXACT, "adults": adults, "minors": minors})


def test_the_budget_may_give_one_end_or_both():
    only_min = TravelRequestCreate(**EXACT, budget_min=5_000_000)
    both = TravelRequestCreate(**EXACT, budget_min=6_000_000, budget_max=8_000_000)

    assert only_min.budget_max is None
    assert both.budget_max == 8_000_000


@pytest.mark.parametrize(
    "budget",
    [
        {"budget_min": 6_000_000.5},
        {"budget_min": "6000000"},
        {"budget_min": 0},
        {"budget_max": True},
        {"budget_max": 1_000_000_000_000},
    ],
    ids=["decimals", "text", "zero", "boolean", "too-big"],
)
def test_the_budget_is_a_positive_whole_number_of_pesos(budget):
    assert set(fields(TravelRequestCreate, {**EXACT, **budget})) == set(budget)


def test_the_budget_maximum_cannot_be_below_the_minimum():
    errors = fields(
        TravelRequestCreate, {**EXACT, "budget_min": 8_000_000, "budget_max": 6_000_000}
    )

    assert errors == {"budget_max": ["No puede ser menor que el mínimo."]}


def test_trip_types_come_back_in_order_without_repeats():
    request = TravelRequestCreate(**EXACT, trip_types=["family", "leisure"])

    assert request.trip_types == ["leisure", "family"]
    assert fields(TravelRequestCreate, {**EXACT, "trip_types": ["family", "spa"]}) == {
        "trip_types": ["No es un tipo de viaje válido."]
    }
    assert fields(TravelRequestCreate, {**EXACT, "trip_types": ["family", "family"]}) == {
        "trip_types": ["Hay un tipo de viaje repetido."]
    }


def test_an_unknown_accommodation_category_is_rejected():
    assert "accommodation_category" in fields(
        TravelRequestCreate, {**EXACT, "accommodation_category": "seven_star"}
    )


def test_notes_keep_their_line_breaks():
    request = TravelRequestCreate(**EXACT, notes="Habitación conectada.\r\nSin escalas.")

    assert request.notes == "Habitación conectada.\nSin escalas."


def test_an_undeclared_field_is_an_error():
    assert "status" in fields(TravelRequestCreate, {**EXACT, "status": "quoted"})


def test_an_update_needs_the_version_it_read():
    assert "expected_version" in fields(TravelRequestUpdate, EXACT)
    assert TravelRequestUpdate(**EXACT, expected_version=3).expected_version == 3


def test_closing_with_other_needs_a_note():
    assert fields(TravelRequestClose, {"reason": "other", "expected_version": 1}) == {
        "note": ["Cuéntanos el motivo."]
    }
    assert TravelRequestClose(reason="no_response", expected_version=1).note is None
    assert TravelRequestClose(
        reason="other", note=" Viaje aplazado ", expected_version=1
    ).note == ("Viaje aplazado")


def test_closing_needs_a_known_reason():
    assert "reason" in fields(TravelRequestClose, {"reason": "lost", "expected_version": 1})


def test_filters_default_to_everything_most_recent_first():
    filters = TravelRequestFilters()

    assert filters.status is None
    assert filters.sort == RequestSort.RECENT
    assert TravelRequestFilters(status="pending").status == StatusFilter.PENDING
