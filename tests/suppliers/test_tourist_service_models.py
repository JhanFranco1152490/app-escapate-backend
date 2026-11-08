from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.suppliers.tourist_service_models import RateValidity, validity_status
from tests.factories import ServiceRateFactory, SupplierFactory, TouristServiceFactory

_NOW = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)
_DAY = date(2026, 11, 7)


@contextmanager
def _violates(constraint: str):
    # Se compara el nombre que entrega el driver y no el texto del mensaje, que viene en el
    # idioma del servidor de base de datos.
    with pytest.raises(IntegrityError) as error:
        yield
    assert error.value.orig.diag.constraint_name == constraint


def test_a_service_keeps_its_attributes(session):
    service = TouristServiceFactory(attributes={"lodging_kind": "hotel", "max_capacity": 4})
    session.expire(service)

    assert service.attributes == {"lodging_kind": "hotel", "max_capacity": 4}
    assert service.is_active
    assert service.supplier is not None


def test_a_new_service_starts_at_version_one_and_each_change_adds_one(session):
    service = TouristServiceFactory()
    assert service.version == 1

    service.destination = "San Andrés"
    session.flush()

    assert service.version == 2


def test_saving_a_service_over_a_version_someone_else_changed_fails(session):
    service = TouristServiceFactory()
    session.execute(
        text("UPDATE tourist_service SET version = version + 1 WHERE id = :id"),
        {"id": service.id},
    )

    service.destination = "San Andrés"
    with pytest.raises(StaleDataError):
        session.flush()


@pytest.mark.parametrize(
    "overrides, constraint",
    [
        pytest.param({"service_type": "spa"}, "ck_tourist_service_type", id="unknown-type"),
        pytest.param(
            {"attributes": ["lodging"]}, "ck_tourist_service_attributes", id="attributes-list"
        ),
        pytest.param(
            {"is_active": False}, "ck_tourist_service_deactivated_at", id="inactive-without-date"
        ),
        pytest.param(
            {"deactivated_at": _NOW}, "ck_tourist_service_deactivated_at", id="active-with-date"
        ),
        pytest.param(
            {"is_active": False, "deactivated_at": _NOW},
            "ck_tourist_service_deactivated_by",
            id="inactive-without-who",
        ),
    ],
)
def test_the_database_rejects_an_inconsistent_service(session, overrides, constraint):
    with _violates(constraint):
        TouristServiceFactory(**overrides)


def test_an_inactive_service_keeps_who_deactivated_it(session):
    service = TouristServiceFactory(inactive=True)

    assert not service.is_active
    assert service.deactivated_by is not None


def test_a_rate_keeps_its_amount_and_currency(session):
    rate = ServiceRateFactory(currency="USD", amount=Decimal("1250.5"))
    session.expire(rate)

    assert rate.amount == Decimal("1250.50")
    assert rate.currency == "USD"


def test_a_rate_starts_at_version_one_and_each_change_adds_one(session):
    rate = ServiceRateFactory()
    assert rate.version == 1

    rate.conditions = "Mínimo 2 noches."
    session.flush()

    assert rate.version == 2


@pytest.mark.parametrize(
    "overrides, constraint",
    [
        pytest.param({"amount": Decimal("0")}, "ck_service_rate_amount", id="zero"),
        pytest.param({"amount": Decimal("-1")}, "ck_service_rate_amount", id="negative"),
        pytest.param(
            {"currency": "COP", "amount": Decimal("480000.50")},
            "ck_service_rate_whole_pesos",
            id="pesos-with-cents",
        ),
        pytest.param({"currency": "EUR"}, "ck_service_rate_currency", id="unknown-currency"),
        pytest.param(
            {"charge_unit": "per_hour"}, "ck_service_rate_charge_unit", id="unknown-unit"
        ),
        pytest.param(
            {"valid_from": _DAY, "valid_until": _DAY - timedelta(days=1)},
            "ck_service_rate_validity",
            id="ends-before-it-starts",
        ),
    ],
)
def test_the_database_rejects_an_inconsistent_rate(session, overrides, constraint):
    with _violates(constraint):
        ServiceRateFactory(**overrides)


def test_a_rate_may_end_the_day_it_starts(session):
    rate = ServiceRateFactory(valid_from=_DAY, valid_until=_DAY)

    assert rate.id is not None


def test_a_supplier_with_services_cannot_be_deleted(session):
    service = TouristServiceFactory()

    with _violates("tourist_service_supplier_id_fkey"):
        session.execute(text("DELETE FROM supplier WHERE id = :id"), {"id": service.supplier_id})


def test_a_service_with_rates_cannot_be_deleted(session):
    rate = ServiceRateFactory()

    with _violates("service_rate_tourist_service_id_fkey"):
        session.execute(
            text("DELETE FROM tourist_service WHERE id = :id"), {"id": rate.tourist_service_id}
        )


def test_the_service_factory_uses_one_of_the_supplier_categories(session):
    supplier = SupplierFactory(categories=["tours"])
    service = TouristServiceFactory(supplier=supplier, service_type="tours", attributes={})

    assert service.service_type in supplier.categories


@pytest.mark.parametrize(
    "day, expected",
    [
        pytest.param(date(2026, 12, 14), RateValidity.UPCOMING, id="the-day-before"),
        pytest.param(date(2026, 12, 15), RateValidity.CURRENT, id="the-first-day"),
        pytest.param(date(2027, 1, 15), RateValidity.CURRENT, id="the-last-day"),
        pytest.param(date(2027, 1, 16), RateValidity.EXPIRED, id="the-day-after"),
    ],
)
def test_a_rate_is_current_from_its_first_to_its_last_day(day, expected):
    assert validity_status(date(2026, 12, 15), date(2027, 1, 15), day) == expected


def test_a_rate_without_an_end_is_current_forever():
    assert validity_status(date(2026, 1, 1), None, date(2040, 1, 1)) == RateValidity.CURRENT
