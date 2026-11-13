from app.suppliers.models import SupplierCategory
from app.suppliers.service_types import (
    CHARGE_UNITS,
    SERVICE_TYPE_LABELS,
    ChargeUnit,
    Currency,
    ServiceType,
)


def test_service_types_are_the_supplier_categories():
    assert ServiceType is SupplierCategory


def test_every_service_type_has_charge_units():
    assert set(CHARGE_UNITS) == set(ServiceType)
    assert all(CHARGE_UNITS.values())


def test_every_charge_unit_is_used_by_some_type():
    used = {unit for units in CHARGE_UNITS.values() for unit in units}
    assert used == set(ChargeUnit)


def test_a_type_does_not_repeat_charge_units():
    for units in CHARGE_UNITS.values():
        assert len(set(units)) == len(units)


def test_the_first_charge_unit_is_the_one_of_the_mockup():
    assert CHARGE_UNITS[ServiceType.LODGING][0] == ChargeUnit.PER_NIGHT


def test_every_service_type_has_a_spanish_label():
    assert set(SERVICE_TYPE_LABELS) == set(ServiceType)
    assert SERVICE_TYPE_LABELS[ServiceType.LODGING] == "Alojamiento"


def test_rates_are_in_pesos_or_dollars():
    assert [currency.value for currency in Currency] == ["COP", "USD"]
