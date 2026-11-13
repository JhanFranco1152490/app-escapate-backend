from datetime import date, timedelta

import pytest

from app.common.errors import NotFound
from app.common.pagination import PageParams
from app.suppliers import tourist_service_models
from app.suppliers.errors import ServiceTypeNotOffered
from app.suppliers.service_attributes import LodgingAttributes
from app.suppliers.services import tourist_service_queries
from tests.factories import (
    ServiceRateFactory,
    SupplierFactory,
    TouristServiceFactory,
    UserAccountFactory,
)
from tests.http import fake_request
from tests.statements import recorded_statements

TODAY = date(2026, 11, 7)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(tourist_service_queries, "today", lambda: TODAY)
    monkeypatch.setattr(tourist_service_models, "today", lambda: TODAY)


def services_of(session, supplier_id: int):
    params = PageParams(page=1, page_size=50)
    return tourist_service_queries.list_supplier_services(
        session, supplier_id, params, fake_request()
    )


def names(page) -> list[str]:
    return [item.name for item in page.results]


def _rates(service):
    """Una vigente, una próxima, una vencida y una sin fecha final: cuentan dos."""
    ServiceRateFactory(tourist_service=service, valid_from=TODAY - timedelta(days=10))
    ServiceRateFactory(tourist_service=service, valid_from=TODAY + timedelta(days=1))
    ServiceRateFactory(
        tourist_service=service,
        valid_from=TODAY - timedelta(days=30),
        valid_until=TODAY - timedelta(days=1),
    )
    ServiceRateFactory(
        tourist_service=service, valid_from=TODAY - timedelta(days=5), valid_until=TODAY
    )


def test_the_list_has_only_the_services_of_that_supplier(session):
    supplier = SupplierFactory()
    TouristServiceFactory(supplier=supplier, name="Habitación doble")
    TouristServiceFactory(name="De otro proveedor")

    assert names(services_of(session, supplier.id)) == ["Habitación doble"]


def test_active_services_come_first_then_by_name_without_accents(session):
    supplier = SupplierFactory()
    for name in ("Zafiro suite", "Ático", "Bahía"):
        TouristServiceFactory(supplier=supplier, name=name)
    TouristServiceFactory(supplier=supplier, name="Alfa", inactive=True)

    assert names(services_of(session, supplier.id)) == ["Ático", "Bahía", "Zafiro suite", "Alfa"]


def test_each_service_counts_its_current_rates(session):
    supplier = SupplierFactory()
    with_rates = TouristServiceFactory(supplier=supplier, name="A con tarifas")
    _rates(with_rates)
    TouristServiceFactory(supplier=supplier, name="B sin tarifas")

    counts = {
        item.name: item.current_rate_count for item in services_of(session, supplier.id).results
    }

    assert counts == {"A con tarifas": 2, "B sin tarifas": 0}


def test_a_supplier_without_services_has_an_empty_list(session):
    assert services_of(session, SupplierFactory().id).count == 0


def test_the_list_of_an_unknown_supplier_is_not_found(session):
    with pytest.raises(NotFound):
        services_of(session, 999_999_999)


def test_the_list_needs_the_supplier_the_count_and_the_page(session):
    supplier = SupplierFactory()
    for _ in range(3):
        _rates(TouristServiceFactory(supplier=supplier))
    session.expunge_all()

    with recorded_statements(session) as statements:
        page = services_of(session, supplier.id)

    assert page.count == 3
    assert len(statements) == 3


def test_the_detail_brings_its_supplier_attributes_and_rate_count(session):
    service = TouristServiceFactory(
        attributes={"lodging_kind": "resort", "max_capacity": 4, "includes": ["wifi"]}
    )
    _rates(service)

    detail = tourist_service_queries.get_tourist_service(session, service.id)

    assert isinstance(detail.attributes, LodgingAttributes)
    assert detail.attributes.max_capacity == 4
    assert detail.supplier.id == service.supplier_id
    assert detail.current_rate_count == 2


def test_the_detail_loads_everything_in_one_query(session):
    manager = UserAccountFactory()
    service = TouristServiceFactory(created_by=manager, inactive=True)
    session.expunge_all()

    with recorded_statements(session) as statements:
        detail = tourist_service_queries.get_tourist_service(session, service.id)

    assert detail.deactivated_by.id == manager.id
    assert len(statements) == 1


def test_an_unknown_service_is_not_found(session):
    with pytest.raises(NotFound):
        tourist_service_queries.get_tourist_service(session, 999_999_999)


def test_the_type_not_offered_error_names_the_type_in_spanish():
    error = ServiceTypeNotOffered("cruise")

    assert error.fields == {
        "service_type": [
            "El proveedor no tiene la clasificación Cruceros. Agrégala en su ficha antes de "
            "registrar este servicio."
        ]
    }
