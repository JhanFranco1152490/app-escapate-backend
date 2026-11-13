from datetime import date, timedelta

import pytest

from app.common.errors import NotFound
from app.common.pagination import PageParams
from app.suppliers import tourist_service_models
from app.suppliers.services import rate_queries
from tests.factories import ServiceRateFactory, TouristServiceFactory
from tests.http import fake_request
from tests.statements import recorded_statements

TODAY = date(2026, 11, 7)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(rate_queries, "today", lambda: TODAY)
    monkeypatch.setattr(tourist_service_models, "today", lambda: TODAY)


def rates_of(session, service_id: int):
    params = PageParams(page=1, page_size=100)
    return rate_queries.list_service_rates(session, service_id, params, fake_request())


def _days(n: int) -> date:
    return TODAY + timedelta(days=n)


def test_current_rates_come_first_then_upcoming_then_expired(session):
    service = TouristServiceFactory()
    ServiceRateFactory(
        tourist_service=service, name="Vencida", valid_from=_days(-60), valid_until=_days(-1)
    )
    ServiceRateFactory(tourist_service=service, name="Próxima", valid_from=_days(1))
    ServiceRateFactory(tourist_service=service, name="Persona adicional", valid_from=_days(-90))
    ServiceRateFactory(
        tourist_service=service, name="Temporada alta", valid_from=_days(-10), valid_until=_days(0)
    )

    page = rates_of(session, service.id)

    assert [(rate.name, rate.validity_status) for rate in page.results] == [
        ("Persona adicional", "current"),
        ("Temporada alta", "current"),
        ("Próxima", "upcoming"),
        ("Vencida", "expired"),
    ]


def test_rates_that_start_the_same_day_are_ordered_by_name_without_accents(session):
    service = TouristServiceFactory()
    for name in ("Niños", "Adultos", "Ático"):
        ServiceRateFactory(tourist_service=service, name=name, valid_from=TODAY)

    assert [rate.name for rate in rates_of(session, service.id).results] == [
        "Adultos",
        "Ático",
        "Niños",
    ]


def test_the_list_has_only_the_rates_of_that_service(session):
    service = TouristServiceFactory()
    ServiceRateFactory(tourist_service=service, name="Propia")
    ServiceRateFactory(name="De otro servicio")

    assert [rate.name for rate in rates_of(session, service.id).results] == ["Propia"]


def test_the_rates_of_an_unknown_service_are_not_found(session):
    with pytest.raises(NotFound):
        rates_of(session, 999_999_999)


def test_the_list_does_not_query_once_per_rate(session):
    service = TouristServiceFactory()
    for _ in range(4):
        ServiceRateFactory(tourist_service=service)
    session.expunge_all()

    with recorded_statements(session) as statements:
        page = rates_of(session, service.id)
        [rate.created_by.full_name for rate in page.results]

    assert page.count == 4
    assert len(statements) == 3


def test_a_rate_is_found_through_its_service(session):
    rate = ServiceRateFactory()

    assert rate_queries.get_service_rate(session, rate.tourist_service_id, rate.id).id == rate.id


def test_a_rate_of_another_service_is_not_found(session):
    rate = ServiceRateFactory()
    other = TouristServiceFactory()

    with pytest.raises(NotFound):
        rate_queries.get_service_rate(session, other.id, rate.id)


def test_an_unknown_rate_is_not_found(session):
    with pytest.raises(NotFound):
        rate_queries.get_service_rate(session, TouristServiceFactory().id, 999_999_999)
