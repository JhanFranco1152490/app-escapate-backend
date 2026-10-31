from datetime import datetime, timezone

import pytest

from app.common.errors import NotFound, StaleVersion
from app.suppliers.errors import DuplicateSupplier
from app.suppliers.schemas import SupplierCreate, SupplierStatusChange, SupplierUpdate
from app.suppliers.services import supplier_management
from tests.factories import SupplierFactory, UserAccountFactory

HOTEL = {
    "trade_name": "Hotel Caribe Azul",
    "document_type": "NIT",
    "document_number": "800.197.268-4",
    "categories": ["lodging"],
    "contact_name": "Andrea Pérez",
    "contact_phone": "300 111 2233",
}
FOREIGN = {
    "trade_name": "Naviera del Sol",
    "document_type": "FOREIGN",
    "document_number": "12-3456789",
    "categories": ["cruise"],
    "contact_name": "Julián Prieto",
    "contact_email": "julian@example.com",
}
_EDITABLE = (
    "trade_name",
    "legal_name",
    "document_type",
    "document_number",
    "categories",
    "city",
    "coverage_zone",
    "contact_name",
    "contact_role",
    "contact_phone",
    "contact_email",
    "payment_terms",
    "commission_rate",
    "agreement_valid_until",
    "notes",
)


@pytest.fixture
def manager(session):
    return UserAccountFactory(first_name="Laura", last_name="Rojas")


def create(session, actor, **data):
    return supplier_management.create_supplier(session, actor, SupplierCreate(**data))


def update(session, supplier, **changes):
    current = {name: getattr(supplier, name) for name in _EDITABLE}
    data = SupplierUpdate(**current | {"expected_version": supplier.version} | changes)
    return supplier_management.update_supplier(session, supplier.id, data)


def deactivate(session, actor, supplier, version=None):
    data = SupplierStatusChange(expected_version=version or supplier.version)
    return supplier_management.deactivate_supplier(session, actor, supplier.id, data)


def activate(session, supplier, version=None):
    data = SupplierStatusChange(expected_version=version or supplier.version)
    return supplier_management.activate_supplier(session, supplier.id, data)


# --- Alta -----------------------------------------------------------------------------------


def test_a_supplier_with_a_nit_is_registered_active_with_who_registered_it(session, manager):
    supplier = create(session, manager, **HOTEL)

    assert supplier.document_number == "8001972684"
    assert supplier.is_active and supplier.deactivated_at is None
    assert supplier.created_by.full_name == "Laura Rojas"
    assert supplier.version == 1


def test_a_supplier_from_abroad_is_registered_with_its_foreign_id(session, manager):
    supplier = create(session, manager, **FOREIGN)

    assert (supplier.document_type, supplier.document_number) == ("FOREIGN", "123456789")


def test_many_suppliers_can_be_registered_without_a_document(session, manager):
    no_document = HOTEL | {"document_type": None, "document_number": None}

    first = create(session, manager, **no_document)
    second = create(session, manager, **no_document)

    assert first.id != second.id


def test_a_repeated_document_written_another_way_is_rejected(session, manager):
    create(session, manager, **HOTEL)

    with pytest.raises(DuplicateSupplier):
        create(session, manager, **HOTEL | {"trade_name": "Otro", "document_number": "8001972684"})


def test_the_same_number_with_another_type_is_another_supplier(session, manager):
    create(session, manager, **FOREIGN | {"document_type": "CE", "document_number": "AB12345"})
    other = create(session, manager, **FOREIGN | {"document_number": "AB12345"})

    assert other.id is not None


def test_a_document_taken_after_the_check_is_still_a_field_error(
    session, manager, monkeypatch, caplog
):
    create(session, manager, **HOTEL)
    # Como si otra petición hubiera guardado el mismo documento después de la revisión.
    monkeypatch.setattr(supplier_management, "_ensure_document_is_free", lambda *args: None)

    with caplog.at_level("DEBUG"), pytest.raises(DuplicateSupplier) as error:
        create(session, manager, **HOTEL)

    # El error de la base trae el documento: no se encadena ni llega al log.
    assert error.value.__cause__ is None and error.value.__suppress_context__
    assert "8001972684" not in caplog.text


# --- Edición --------------------------------------------------------------------------------


def test_editing_keeps_the_new_data_and_adds_a_version(session, manager):
    supplier = create(session, manager, **HOTEL)

    edited = update(session, supplier, city="Cartagena", categories=["tours", "lodging"])

    assert (edited.city, edited.categories, edited.version) == (
        "Cartagena",
        ["lodging", "tours"],
        2,
    )
    assert edited.created_by.full_name == "Laura Rojas"


def test_editing_with_an_old_version_is_stale(session, manager):
    supplier = create(session, manager, **HOTEL)
    update(session, supplier, city="Cartagena")

    with pytest.raises(StaleVersion):
        update(session, supplier, city="Bogotá", expected_version=1)


def test_its_own_document_is_not_a_repeat(session, manager):
    supplier = create(session, manager, **HOTEL)

    assert update(session, supplier, notes="Sin cambios de documento").version == 2


def test_editing_into_the_document_of_another_supplier_is_rejected(session, manager):
    create(session, manager, **HOTEL)
    other = create(session, manager, **FOREIGN)

    with pytest.raises(DuplicateSupplier):
        update(session, other, document_type="NIT", document_number="800.197.268-4")


def test_an_inactive_supplier_can_be_edited_and_stays_inactive(session):
    supplier = SupplierFactory(inactive=True)

    edited = update(session, supplier, city="Cartagena")

    assert (edited.city, edited.is_active) == ("Cartagena", False)


def test_editing_an_unknown_supplier_is_not_found(session):
    with pytest.raises(NotFound):
        supplier_management.update_supplier(
            session, 999_999_999, SupplierUpdate(**HOTEL, expected_version=1)
        )


# --- Desactivar y activar -------------------------------------------------------------------


def test_deactivating_records_who_and_when(session, manager):
    supplier = create(session, manager, **HOTEL)
    before = datetime.now(timezone.utc)

    deactivated = deactivate(session, manager, supplier)

    assert not deactivated.is_active
    assert deactivated.deactivated_at >= before
    assert deactivated.deactivated_by.full_name == "Laura Rojas"
    assert deactivated.version == 2


def test_deactivating_twice_changes_nothing(session, manager):
    supplier = deactivate(session, manager, create(session, manager, **HOTEL))
    first_time = supplier.deactivated_at

    again = deactivate(session, UserAccountFactory(), supplier)

    assert (again.deactivated_at, again.deactivated_by.full_name) == (first_time, "Laura Rojas")
    assert again.version == 2


def test_activating_clears_who_and_when(session, manager):
    supplier = deactivate(session, manager, create(session, manager, **HOTEL))

    activated = activate(session, supplier)

    assert activated.is_active
    assert (activated.deactivated_at, activated.deactivated_by) == (None, None)
    assert activated.version == 3


def test_activating_an_active_supplier_changes_nothing(session, manager):
    supplier = create(session, manager, **HOTEL)

    assert activate(session, supplier).version == 1


def test_deactivating_with_an_old_version_is_stale(session, manager):
    supplier = create(session, manager, **HOTEL)
    update(session, supplier, city="Cartagena")

    with pytest.raises(StaleVersion):
        deactivate(session, manager, supplier, version=1)


def test_activating_with_an_old_version_is_stale(session, manager):
    supplier = deactivate(session, manager, create(session, manager, **HOTEL))
    update(session, supplier, city="Cartagena")

    with pytest.raises(StaleVersion):
        activate(session, supplier, version=2)


def test_changing_the_status_of_an_unknown_supplier_is_not_found(session, manager):
    data = SupplierStatusChange(expected_version=1)

    with pytest.raises(NotFound):
        supplier_management.deactivate_supplier(session, manager, 999_999_999, data)
    with pytest.raises(NotFound):
        supplier_management.activate_supplier(session, 999_999_999, data)
