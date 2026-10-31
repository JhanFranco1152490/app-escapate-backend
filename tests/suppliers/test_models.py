from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.suppliers import models
from tests.factories import SupplierFactory, UserAccountFactory


@contextmanager
def _violates(constraint: str):
    # Se compara el nombre que entrega el driver y no el texto del mensaje, que viene en el
    # idioma del servidor de base de datos.
    with pytest.raises(IntegrityError) as error:
        yield
    assert error.value.orig.diag.constraint_name == constraint


def test_a_supplier_keeps_its_categories_and_commission(session):
    supplier = SupplierFactory(categories=["lodging", "tours"], commission_rate=Decimal("10.5"))
    session.expire(supplier)

    assert supplier.categories == ["lodging", "tours"]
    assert supplier.commission_rate == Decimal("10.50")
    assert supplier.is_active


def test_a_new_supplier_starts_at_version_one_and_each_change_adds_one(session):
    supplier = SupplierFactory()
    assert supplier.version == 1

    supplier.city = "Cartagena"
    session.flush()

    assert supplier.version == 2


def test_saving_over_a_version_someone_else_already_changed_fails(session):
    supplier = SupplierFactory()
    session.execute(
        text("UPDATE supplier SET version = version + 1 WHERE id = :id"), {"id": supplier.id}
    )

    supplier.city = "Cartagena"
    with pytest.raises(StaleDataError):
        session.flush()


_NOW = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "overrides, constraint",
    [
        pytest.param({"categories": []}, "ck_supplier_categories", id="no-categories"),
        pytest.param(
            {"categories": ["lodging", "spa"]}, "ck_supplier_categories", id="unknown-category"
        ),
        pytest.param(
            {"contact_phone": None, "contact_email": None},
            "ck_supplier_contact",
            id="no-phone-nor-email",
        ),
        pytest.param(
            {"commission_rate": Decimal("100.01")},
            "ck_supplier_commission_rate",
            id="commission-over-100",
        ),
        pytest.param(
            {"commission_rate": Decimal("-0.01")},
            "ck_supplier_commission_rate",
            id="negative-commission",
        ),
        pytest.param(
            {"document_type": "TI", "document_number": "1098221334"},
            "ck_supplier_document_type",
            id="document-type-of-travelers-only",
        ),
        pytest.param(
            {"document_type": "NIT", "document_number": None},
            "ck_supplier_document_pair",
            id="type-without-number",
        ),
        pytest.param(
            {"document_type": None, "document_number": "A1234567"},
            "ck_supplier_document_pair",
            id="number-without-type",
        ),
        pytest.param(
            {"is_active": False}, "ck_supplier_deactivated_at", id="inactive-without-date"
        ),
        pytest.param(
            {"deactivated_at": _NOW}, "ck_supplier_deactivated_at", id="active-with-date"
        ),
        pytest.param(
            {"is_active": False, "deactivated_at": _NOW},
            "ck_supplier_deactivated_by",
            id="inactive-without-who",
        ),
    ],
)
def test_the_database_rejects_an_inconsistent_supplier(session, overrides, constraint):
    with _violates(constraint):
        SupplierFactory(**overrides)


def test_a_supplier_with_only_an_email_is_accepted(session):
    supplier = SupplierFactory(contact_phone=None, contact_email="reservas@example.com")

    assert supplier.id is not None


def test_an_inactive_supplier_keeps_who_deactivated_it(session):
    supplier = SupplierFactory(inactive=True)

    assert not supplier.is_active
    assert supplier.deactivated_by is not None


def test_the_supplier_document_is_unique_per_type(session):
    SupplierFactory(document_type="FOREIGN", document_number="A1234567")

    with _violates("uq_supplier_document"):
        SupplierFactory(document_type="FOREIGN", document_number="A1234567")


def test_the_same_number_with_another_type_is_another_supplier(session):
    SupplierFactory(document_type="CC", document_number="10900001")
    other = SupplierFactory(document_type="CE", document_number="10900001")

    assert other.id is not None


def test_many_suppliers_can_be_saved_without_a_document(session):
    first = SupplierFactory(document_type=None, document_number=None)
    second = SupplierFactory(document_type=None, document_number=None)

    assert first.id != second.id


def test_a_user_who_registered_suppliers_cannot_be_deleted(session):
    user = UserAccountFactory()
    SupplierFactory(created_by=user)

    with _violates("supplier_created_by_id_fkey"):
        session.delete(user)
        session.flush()


@pytest.mark.parametrize(
    "valid_until, expired",
    [
        pytest.param(None, False, id="no-agreement-date"),
        pytest.param(date(2026, 10, 30), False, id="ends-today"),
        pytest.param(date(2026, 10, 29), True, id="ended-yesterday"),
    ],
)
def test_the_agreement_expires_the_day_after_with_the_bogota_date(
    session, monkeypatch, valid_until, expired
):
    monkeypatch.setattr(models, "today", lambda: date(2026, 10, 30))
    supplier = SupplierFactory(agreement_valid_until=valid_until)

    assert supplier.agreement_expired is expired
