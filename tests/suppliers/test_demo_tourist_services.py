from decimal import Decimal

import pytest
from sqlmodel import select

from app.suppliers.demo_data import DEMO_TOURIST_SERVICES
from app.suppliers.services.demo_suppliers import seed_demo_suppliers
from app.suppliers.services.demo_tourist_services import seed_demo_tourist_services
from app.suppliers.tourist_service_models import RateValidity, ServiceRate, TouristService
from tests.factories import UserAccountFactory


@pytest.fixture
def actor(session):
    actor = UserAccountFactory()
    seed_demo_suppliers(session, actor)
    return actor


def _service(session, name: str) -> TouristService:
    return session.exec(select(TouristService).where(TouristService.name == name)).one()


def _rates(session, service: TouristService) -> list[ServiceRate]:
    statement = select(ServiceRate).where(ServiceRate.tourist_service_id == service.id)
    return list(session.exec(statement))


def test_it_loads_every_demo_service_with_its_supplier_and_author(session, actor):
    records = seed_demo_tourist_services(session, actor)

    services = session.exec(select(TouristService)).all()
    assert len(services) == len(DEMO_TOURIST_SERVICES)
    assert all(service.created_by_id == actor.id for service in services)
    assert all(record.created and record.kind == "Servicio" for record in records)
    assert "Habitación familiar (Hotel Demostración)" in {record.label for record in records}


def test_the_lodging_has_a_rate_in_each_state(session, actor):
    seed_demo_tourist_services(session, actor)

    rates = _rates(session, _service(session, "Habitación familiar"))

    assert sorted(rate.validity_status for rate in rates) == sorted(
        [RateValidity.CURRENT, RateValidity.CURRENT, RateValidity.UPCOMING, RateValidity.EXPIRED]
    )
    assert any(rate.valid_until is None for rate in rates)


def test_the_cruise_has_a_rate_in_dollars_with_cents(session, actor):
    seed_demo_tourist_services(session, actor)

    (rate,) = _rates(session, _service(session, "Caribe occidental 7 noches"))

    assert rate.currency == "USD"
    assert rate.amount != rate.amount.to_integral_value()
    assert rate.amount > Decimal("0")


def test_there_is_an_inactive_service_that_keeps_its_rate(session, actor):
    seed_demo_tourist_services(session, actor)

    transfer = _service(session, "Traslado aeropuerto – hotel")

    assert not transfer.is_active
    assert transfer.deactivated_by_id == actor.id
    assert len(_rates(session, transfer)) == 1


def test_the_demo_services_cover_several_types(session, actor):
    seed_demo_tourist_services(session, actor)

    types = {service.service_type for service in session.exec(select(TouristService))}

    assert types == {"lodging", "ground", "tours", "cruise"}


def test_loading_it_again_skips_every_service_and_adds_no_rates(session, actor):
    seed_demo_tourist_services(session, actor)
    rates_before = len(session.exec(select(ServiceRate)).all())

    records = seed_demo_tourist_services(session, actor)

    assert not any(record.created for record in records)
    assert len(session.exec(select(TouristService)).all()) == len(DEMO_TOURIST_SERVICES)
    assert len(session.exec(select(ServiceRate)).all()) == rates_before
