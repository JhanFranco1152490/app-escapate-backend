import pytest

from app.common.errors import NotFound, StaleVersion
from app.suppliers.errors import ServiceTypeChanged, ServiceTypeNotOffered, SupplierInactive
from app.suppliers.service_types import ServiceType
from app.suppliers.services import tourist_service_management as management
from app.suppliers.tourist_service_models import TouristService
from app.suppliers.tourist_service_schemas import (
    TouristServiceCreate,
    TouristServiceStatusChange,
    TouristServiceUpdate,
)
from tests.factories import SupplierFactory, TouristServiceFactory, UserAccountFactory
from tests.suppliers.samples import MINIMAL

ALL_TYPES = [member.value for member in ServiceType]


def _data(service_type: str = "lodging", **overrides) -> dict:
    return {
        "service_type": service_type,
        "name": "Servicio de prueba",
        "destination": "Cartagena",
        "attributes": MINIMAL[ServiceType(service_type)],
    } | overrides


def _create(session, supplier, actor=None, **data):
    actor = actor or UserAccountFactory()
    return management.create_tourist_service(
        session, actor, supplier.id, TouristServiceCreate(**_data(**data))
    )


def _update(session, service, **data):
    body = _data(service.service_type) | {"expected_version": service.version} | data
    return management.update_tourist_service(session, service.id, TouristServiceUpdate(**body))


def _status(version: int) -> TouristServiceStatusChange:
    return TouristServiceStatusChange(expected_version=version)


@pytest.mark.parametrize("service_type", ALL_TYPES)
def test_a_service_of_each_type_is_registered_for_its_supplier(session, service_type):
    supplier = SupplierFactory(categories=ALL_TYPES)
    actor = UserAccountFactory()

    detail = _create(session, supplier, actor, service_type=service_type)

    assert detail.supplier.id == supplier.id
    assert detail.service_type == service_type
    assert detail.is_active
    assert detail.created_by.id == actor.id
    assert detail.version == 1


def test_what_is_stored_leaves_out_the_optional_fields_not_filled(session):
    supplier = SupplierFactory()

    detail = _create(session, supplier, attributes={"lodging_kind": "hotel", "max_capacity": 2})

    assert session.get(TouristService, detail.id).attributes == {
        "lodging_kind": "hotel",
        "max_capacity": 2,
        "includes": [],
    }


def test_a_type_the_supplier_does_not_offer_is_rejected(session):
    supplier = SupplierFactory(categories=["lodging"])

    with pytest.raises(ServiceTypeNotOffered):
        _create(session, supplier, service_type="tours")


def test_an_inactive_supplier_gets_no_new_services(session):
    supplier = SupplierFactory(inactive=True)

    with pytest.raises(SupplierInactive):
        _create(session, supplier)


def test_an_unknown_supplier_is_not_found(session):
    with pytest.raises(NotFound):
        management.create_tourist_service(
            session, UserAccountFactory(), 999_999_999, TouristServiceCreate(**_data())
        )


def test_removing_a_category_from_the_supplier_keeps_its_services_editable(session):
    supplier = SupplierFactory(categories=["lodging", "tours"])
    service = TouristServiceFactory(
        supplier=supplier,
        service_type="tours",
        attributes={
            "duration_value": 4,
            "duration_unit": "hours",
        },
    )
    supplier.categories = ["lodging"]
    session.flush()

    detail = _update(session, service, name="Tour renombrado")

    assert (detail.service_type, detail.name) == ("tours", "Tour renombrado")


def test_editing_keeps_the_changes_and_adds_a_version(session):
    service = TouristServiceFactory()

    detail = _update(
        session,
        service,
        name="Habitación familiar",
        destination="San Andrés",
        conditions="Sin reembolso.",
        attributes={"lodging_kind": "resort", "max_capacity": 6, "includes": ["wifi"]},
    )

    assert (detail.name, detail.destination, detail.conditions) == (
        "Habitación familiar",
        "San Andrés",
        "Sin reembolso.",
    )
    assert detail.attributes.max_capacity == 6
    assert detail.version == 2


def test_editing_over_an_old_version_is_rejected(session):
    service = TouristServiceFactory()

    with pytest.raises(StaleVersion):
        _update(session, service, expected_version=service.version + 1)


def test_the_type_cannot_change(session):
    supplier = SupplierFactory(categories=["lodging", "tours"])
    service = TouristServiceFactory(supplier=supplier)

    with pytest.raises(ServiceTypeChanged):
        _update(session, service, **_data("tours"))


def test_an_old_version_is_reported_before_a_changed_type(session):
    service = TouristServiceFactory()

    with pytest.raises(StaleVersion):
        _update(session, service, **_data("tours"), expected_version=service.version + 1)


def test_an_inactive_service_of_an_inactive_supplier_can_be_edited(session):
    service = TouristServiceFactory(supplier=SupplierFactory(inactive=True), inactive=True)

    detail = _update(session, service, name="Corregido")

    assert detail.name == "Corregido"
    assert not detail.is_active


def test_editing_an_unknown_service_is_not_found(session):
    body = TouristServiceUpdate(**_data(), expected_version=1)

    with pytest.raises(NotFound):
        management.update_tourist_service(session, 999_999_999, body)


def test_deactivating_keeps_who_and_when(session):
    service = TouristServiceFactory()
    actor = UserAccountFactory()

    detail = management.deactivate_tourist_service(session, actor, service.id, _status(1))

    assert not detail.is_active
    assert detail.deactivated_by.id == actor.id
    assert detail.deactivated_at is not None


def test_deactivating_twice_changes_nothing(session):
    service = TouristServiceFactory(inactive=True)
    before = (service.deactivated_at, service.version)

    detail = management.deactivate_tourist_service(
        session, UserAccountFactory(), service.id, _status(service.version)
    )

    assert (detail.deactivated_at, detail.version) == before


def test_activating_clears_who_and_when(session):
    service = TouristServiceFactory(inactive=True)

    detail = management.activate_tourist_service(session, service.id, _status(service.version))

    assert detail.is_active
    assert (detail.deactivated_at, detail.deactivated_by) == (None, None)


def test_a_service_of_an_inactive_supplier_cannot_be_activated(session):
    service = TouristServiceFactory(supplier=SupplierFactory(inactive=True), inactive=True)

    with pytest.raises(SupplierInactive):
        management.activate_tourist_service(session, service.id, _status(service.version))


@pytest.mark.parametrize("inactive", [False, True])
def test_changing_the_status_over_an_old_version_is_rejected(session, inactive):
    service = TouristServiceFactory(inactive=inactive)
    stale = _status(service.version + 1)

    with pytest.raises(StaleVersion):
        management.deactivate_tourist_service(session, UserAccountFactory(), service.id, stale)
    with pytest.raises(StaleVersion):
        management.activate_tourist_service(session, service.id, stale)
