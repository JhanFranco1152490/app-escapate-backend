from decimal import Decimal

import pytest
from sqlmodel import select

from app.common.errors import NotFound, StaleVersion
from app.suppliers.errors import ChargeUnitNotAllowed, ServiceInactive
from app.suppliers.rate_schemas import ServiceRateCreate, ServiceRateUpdate
from app.suppliers.services import rate_management
from app.suppliers.tourist_service_models import ServiceRate
from tests.factories import ServiceRateFactory, TouristServiceFactory, UserAccountFactory

RATE = {
    "name": "Temporada alta",
    "valid_from": "2026-12-15",
    "valid_until": "2027-01-15",
    "currency": "COP",
    "charge_unit": "per_night",
    "amount": "710000",
}


def _create(session, service, actor=None, **data):
    actor = actor or UserAccountFactory()
    return rate_management.create_service_rate(
        session, actor, service.id, ServiceRateCreate(**(RATE | data))
    )


def _update(session, rate, **data):
    body = RATE | {"expected_version": rate.version} | data
    return rate_management.update_service_rate(
        session, rate.tourist_service_id, rate.id, ServiceRateUpdate(**body)
    )


def test_a_rate_in_pesos_is_registered_for_its_service(session):
    service = TouristServiceFactory()
    actor = UserAccountFactory()

    rate = _create(session, service, actor, conditions="Mínimo 5 noches.")

    assert rate.tourist_service_id == service.id
    assert (rate.amount, rate.currency, rate.conditions) == (
        Decimal("710000"),
        "COP",
        "Mínimo 5 noches.",
    )
    assert rate.created_by.id == actor.id


def test_a_rate_in_dollars_keeps_its_cents(session):
    rate = _create(session, TouristServiceFactory(), currency="USD", amount="1250.50")
    session.expire_all()

    assert session.get(ServiceRate, rate.id).amount == Decimal("1250.50")


def test_a_rate_without_an_end_is_registered(session):
    rate = _create(session, TouristServiceFactory(), valid_until=None)

    assert rate.valid_until is None


def test_a_charge_unit_of_another_type_is_rejected(session):
    with pytest.raises(ChargeUnitNotAllowed):
        _create(session, TouristServiceFactory(), charge_unit="per_cabin")


def test_an_inactive_service_gets_no_new_rates(session):
    with pytest.raises(ServiceInactive):
        _create(session, TouristServiceFactory(inactive=True))


def test_a_rate_for_an_unknown_service_is_not_found(session):
    with pytest.raises(NotFound):
        rate_management.create_service_rate(
            session, UserAccountFactory(), 999_999_999, ServiceRateCreate(**RATE)
        )


def test_editing_keeps_the_new_value_and_conditions(session):
    rate = ServiceRateFactory()

    updated = _update(session, rate, amount="760000", conditions="Mínimo 3 noches.")

    assert (updated.amount, updated.conditions) == (Decimal("760000"), "Mínimo 3 noches.")
    assert updated.version == 2


def test_editing_over_an_old_version_is_rejected(session):
    rate = ServiceRateFactory()

    with pytest.raises(StaleVersion):
        _update(session, rate, expected_version=rate.version + 1)


def test_editing_with_a_charge_unit_of_another_type_is_rejected(session):
    rate = ServiceRateFactory()

    with pytest.raises(ChargeUnitNotAllowed):
        _update(session, rate, charge_unit="per_trip")


def test_the_rates_of_an_inactive_service_can_be_edited_and_deleted(session):
    service = TouristServiceFactory(inactive=True)
    first = ServiceRateFactory(tourist_service=service)
    second = ServiceRateFactory(tourist_service=service)

    assert _update(session, first, name="Corregida").name == "Corregida"
    rate_management.delete_service_rate(session, service.id, second.id, second.version)


def test_a_deleted_rate_is_gone(session):
    rate = ServiceRateFactory()
    service_id, rate_id = rate.tourist_service_id, rate.id

    rate_management.delete_service_rate(session, service_id, rate_id, rate.version)

    remaining = select(ServiceRate.id).where(ServiceRate.id == rate_id)
    assert session.exec(remaining).first() is None


def test_deleting_over_an_old_version_is_rejected(session):
    rate = ServiceRateFactory()

    with pytest.raises(StaleVersion):
        rate_management.delete_service_rate(
            session, rate.tourist_service_id, rate.id, rate.version + 1
        )


def test_a_rate_of_another_service_cannot_be_edited_or_deleted(session):
    rate = ServiceRateFactory()
    other = TouristServiceFactory()
    body = ServiceRateUpdate(**RATE, expected_version=rate.version)

    with pytest.raises(NotFound):
        rate_management.update_service_rate(session, other.id, rate.id, body)
    with pytest.raises(NotFound):
        rate_management.delete_service_rate(session, other.id, rate.id, rate.version)
