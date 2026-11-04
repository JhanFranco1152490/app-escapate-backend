from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.suppliers.schemas import (
    SupplierCreate,
    SupplierDetail,
    SupplierFilters,
    SupplierListItem,
    SupplierStatusChange,
    SupplierUpdate,
)
from tests.factories import SupplierFactory, UserAccountFactory

SUPPLIER = {
    "trade_name": "Hotel Caribe Azul",
    "legal_name": "Inversiones Caribe Azul SAS",
    "document_type": "NIT",
    "document_number": "800.197.268-4",
    "categories": ["tours", "lodging"],
    "city": "Cartagena",
    "coverage_zone": "Caribe colombiano",
    "contact_name": "Andrea Pérez",
    "contact_role": "Reservas",
    "contact_phone": "300 111 2233",
    "contact_email": "Reservas@Example.com",
    "payment_terms": "50 % al reservar, saldo 15 días antes",
    "commission_rate": "10.5",
    "agreement_valid_until": "2027-06-30",
    "notes": "Atiende de lunes a sábado.",
}

CONTACT_REQUIRED = "Indica un teléfono o un correo de contacto."


def errors_of(body: dict, model=SupplierCreate) -> dict[str, str]:
    """Campo -> mensaje de cada error al validar `body`."""
    with pytest.raises(ValidationError) as error:
        model(**body)
    return {item["loc"][-1]: item["msg"] for item in error.value.errors()}


def without(*fields: str) -> dict:
    return {name: value for name, value in SUPPLIER.items() if name not in fields}


def test_a_supplier_is_stored_normalized():
    supplier = SupplierCreate(**SUPPLIER)

    assert supplier.document_number == "8001972684"
    assert supplier.contact_phone == "+573001112233"
    assert supplier.contact_email == "reservas@example.com"
    assert supplier.commission_rate == Decimal("10.5")


def test_only_the_trade_name_the_categories_and_a_contact_are_required():
    supplier = SupplierCreate(
        trade_name="Guía Pedro",
        categories=["tours"],
        contact_name="Pedro",
        contact_email="pedro@example.com",
    )

    assert supplier.document_type is None
    assert supplier.contact_phone is None


@pytest.mark.parametrize("field", ["trade_name", "contact_name"])
@pytest.mark.parametrize("value", ["", "   "])
def test_a_required_text_cannot_be_empty(field, value):
    assert errors_of(SUPPLIER | {field: value}) == {field: "Este campo es obligatorio."}


@pytest.mark.parametrize("field", ["legal_name", "city", "coverage_zone", "notes"])
def test_an_empty_optional_text_is_stored_as_none(field):
    assert getattr(SupplierCreate(**SUPPLIER | {field: "  "}), field) is None


def test_a_text_too_long_says_its_limit():
    assert errors_of(SUPPLIER | {"trade_name": "a" * 151}) == {
        "trade_name": "Máximo 150 caracteres."
    }


def test_control_characters_are_rejected():
    assert "contact_name" in errors_of(SUPPLIER | {"contact_name": "Andrea​Pérez"})


# --- Documento ------------------------------------------------------------------------------


def test_a_document_number_needs_its_type():
    assert errors_of(without("document_type")) == {
        "document_number": "Elige también el tipo de documento."
    }


def test_a_document_type_needs_its_number():
    assert errors_of(without("document_number")) == {
        "document_number": "Indica también el número."
    }


def test_a_nit_with_a_wrong_check_digit_has_its_own_message():
    assert errors_of(SUPPLIER | {"document_number": "800.197.268-5"}) == {
        "document_number": "El dígito de verificación del NIT no coincide."
    }


def test_a_foreign_tax_id_loses_its_dash():
    supplier = SupplierCreate(
        **SUPPLIER | {"document_type": "FOREIGN", "document_number": "12-3456789"}
    )

    assert supplier.document_number == "123456789"


@pytest.mark.parametrize("document_type", ["TI", "RC", "PA", "PPT"])
def test_a_document_type_suppliers_do_not_use_is_rejected(document_type):
    assert "document_type" in errors_of(SUPPLIER | {"document_type": document_type})


def test_an_invalid_number_for_its_type():
    assert errors_of(SUPPLIER | {"document_type": "CC", "document_number": "AB12"}) == {
        "document_number": "No es válido para ese tipo."
    }


# --- Clasificación --------------------------------------------------------------------------


def test_the_categories_come_back_in_the_fixed_order():
    supplier = SupplierCreate(**SUPPLIER | {"categories": ["other", "air", "lodging"]})

    assert supplier.categories == ["lodging", "air", "other"]


def test_at_least_one_category_is_required():
    assert errors_of(SUPPLIER | {"categories": []}) == {
        "categories": "Elige al menos una clasificación."
    }
    assert "categories" in errors_of(without("categories"))


def test_a_repeated_category_is_rejected():
    assert errors_of(SUPPLIER | {"categories": ["tours", "tours"]}) == {
        "categories": "Hay una clasificación repetida."
    }


def test_an_unknown_category_is_reported_on_the_field_not_on_its_position():
    assert errors_of(SUPPLIER | {"categories": ["lodging", "spa"]}) == {
        "categories": "No es una clasificación válida."
    }


def test_more_categories_than_the_list_has_are_rejected():
    assert "categories" in errors_of(SUPPLIER | {"categories": ["lodging"] * 9})


# --- Comisión -------------------------------------------------------------------------------


@pytest.mark.parametrize("rate", ["0", "10.5", "99.99", "100", 15])
def test_a_commission_between_zero_and_one_hundred(rate):
    assert SupplierCreate(**SUPPLIER | {"commission_rate": rate}).commission_rate is not None


@pytest.mark.parametrize("rate", ["-0.01", "100.01", "10.123", "diez"])
def test_an_invalid_commission(rate):
    assert "commission_rate" in errors_of(SUPPLIER | {"commission_rate": rate})


# --- Teléfono o correo ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(without("contact_phone", "contact_email"), id="absent"),
        pytest.param(SUPPLIER | {"contact_phone": None, "contact_email": None}, id="null"),
        pytest.param(SUPPLIER | {"contact_phone": "  ", "contact_email": ""}, id="blank"),
    ],
)
def test_a_phone_or_an_email_is_required_and_both_fields_say_so(body):
    assert errors_of(body) == {
        "contact_phone": CONTACT_REQUIRED,
        "contact_email": CONTACT_REQUIRED,
    }


def test_a_blank_contact_is_unfilled_not_invalid():
    with pytest.raises(ValidationError) as error:
        SupplierCreate(**SUPPLIER | {"contact_phone": "  ", "contact_email": " "})

    assert [(item["loc"], item["msg"]) for item in error.value.errors()] == [
        (("contact_phone",), CONTACT_REQUIRED),
        (("contact_email",), CONTACT_REQUIRED),
    ]


def test_the_missing_contact_comes_with_every_other_error():
    body = without("contact_phone", "contact_email") | {"trade_name": "", "extra": 1}

    assert errors_of(body) == {
        "trade_name": "Este campo es obligatorio.",
        "contact_phone": CONTACT_REQUIRED,
        "contact_email": CONTACT_REQUIRED,
        "extra": "Extra inputs are not permitted",
    }


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(without("contact_email"), id="only-phone"),
        pytest.param(without("contact_phone"), id="only-email"),
    ],
)
def test_one_of_the_two_is_enough(body):
    assert SupplierCreate(**body).contact_name == "Andrea Pérez"


def test_an_invalid_email_without_a_phone_only_reports_the_email():
    assert errors_of(without("contact_phone") | {"contact_email": "no-es-correo"}) == {
        "contact_email": "No es un correo válido."
    }


def test_an_invalid_phone_without_an_email_only_reports_the_phone():
    assert errors_of(without("contact_email") | {"contact_phone": "12345"}) == {
        "contact_phone": "No es un teléfono válido para ese país."
    }


def test_a_foreign_phone_is_accepted():
    supplier = SupplierCreate(**SUPPLIER | {"contact_phone": "+1 305 555 0123"})

    assert supplier.contact_phone == "+13055550123"


# --- Edición, estado y filtros --------------------------------------------------------------


def test_editing_needs_the_version_that_was_read():
    assert SupplierUpdate(**SUPPLIER, expected_version=3).expected_version == 3
    assert "expected_version" in errors_of(SUPPLIER | {"expected_version": 0}, SupplierUpdate)
    assert "expected_version" in errors_of(SUPPLIER, SupplierUpdate)


@pytest.mark.parametrize("field", ["is_active", "created_by_id", "expected_version"])
def test_creating_does_not_accept_fields_it_does_not_own(field):
    assert field in errors_of(SUPPLIER | {field: 1})


def test_changing_the_status_only_takes_the_version():
    assert SupplierStatusChange(expected_version=2).expected_version == 2
    assert "is_active" in errors_of(
        {"expected_version": 2, "is_active": False}, SupplierStatusChange
    )


def test_the_filters_show_the_active_suppliers_by_default():
    filters = SupplierFilters()

    assert (filters.q, filters.category, filters.status) == ("", None, "active")


def test_the_filters_reject_an_unknown_category_or_status():
    with pytest.raises(ValidationError):
        SupplierFilters(category="spa")
    with pytest.raises(ValidationError):
        SupplierFilters(status="deleted")


# --- Salida ---------------------------------------------------------------------------------


def test_the_detail_says_who_registered_and_deactivated_it(session):
    manager = UserAccountFactory(first_name="Laura", last_name="Rojas")
    supplier = SupplierFactory(created_by=manager, inactive=True, commission_rate=Decimal("10"))
    session.refresh(supplier)

    detail = SupplierDetail.model_validate(supplier)

    assert detail.created_by.model_dump() == {"id": manager.id, "full_name": "Laura Rojas"}
    assert detail.deactivated_by == detail.created_by
    assert detail.agreement_expired is False
    assert detail.model_dump(mode="json")["commission_rate"] == "10.00"


def test_an_active_supplier_has_nobody_who_deactivated_it(session):
    detail = SupplierDetail.model_validate(SupplierFactory())

    assert (detail.deactivated_at, detail.deactivated_by) == (None, None)


def test_the_list_item_leaves_out_the_commercial_details(session):
    item = SupplierListItem.model_validate(SupplierFactory(notes="Algo", payment_terms="Contado"))

    dumped = item.model_dump()
    assert not {"notes", "payment_terms", "commission_rate"} & dumped.keys()
    assert dumped["categories"] == ["lodging"]
