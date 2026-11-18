from datetime import date, datetime, timedelta, timezone

import pytest

from app.travel_requests import models
from app.travel_requests.schemas import TravelRequestDetail, TravelRequestListItem
from tests.factories import TravelRequestFactory

TODAY = date(2026, 11, 13)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(models, "today", lambda: TODAY)


def _created(day: date, hour_utc: int = 15) -> datetime:
    return datetime(day.year, day.month, day.day, hour_utc, tzinfo=timezone.utc)


def test_the_list_item_shows_the_code_the_client_and_the_advisor(session):
    request = TravelRequestFactory(created_at=_created(TODAY))

    item = TravelRequestListItem.model_validate(request)

    assert item.code == f"SOL-{request.id:04d}"
    assert item.client.display_name == request.client.display_name
    assert item.assigned_to.full_name == request.assigned_to.full_name
    assert item.assigned_to.is_active
    assert item.waiting_days == 0


def test_waiting_days_count_calendar_days_in_bogota(session):
    six_days_ago = TravelRequestFactory(created_at=_created(TODAY - timedelta(days=6)))
    # 23:00 del día anterior en Bogotá son las 04:00 de hoy en UTC: lleva un día esperando.
    last_night = TravelRequestFactory(created_at=_created(TODAY, hour_utc=4))

    assert TravelRequestListItem.model_validate(six_days_ago).waiting_days == 6
    assert TravelRequestListItem.model_validate(last_night).waiting_days == 1


def test_the_detail_brings_everything_and_the_close_data(session):
    request = TravelRequestFactory(
        closed=True,
        created_at=_created(TODAY),
        trip_types=["family"],
        budget_min=6_000_000,
        notes="Sin escalas.",
    )

    detail = TravelRequestDetail.model_validate(request)

    assert detail.trip_types == ["family"]
    assert detail.budget_min == 6_000_000
    assert detail.notes == "Sin escalas."
    assert detail.close_reason == "client_declined"
    assert detail.closed_by.id == request.closed_by.id
    assert detail.created_by.id == request.created_by.id
    assert detail.version == 1


def test_the_list_item_leaves_out_notes_budget_and_preferences():
    hidden = {"notes", "budget_min", "budget_max", "trip_types", "accommodation_category"}

    assert not hidden & set(TravelRequestListItem.model_fields)
