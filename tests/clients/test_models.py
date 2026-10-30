from contextlib import contextmanager
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.clients import models
from tests.factories import ClientFactory, TravelerFactory


@contextmanager
def _violates(constraint: str):
    # Se compara el nombre que entrega el driver y no el texto del mensaje, que viene en el
    # idioma del servidor de base de datos.
    with pytest.raises(IntegrityError) as error:
        yield
    assert error.value.orig.diag.constraint_name == constraint


def test_a_person_and_a_company_are_saved_with_their_display_name(session):
    person = ClientFactory(first_name="Marcela", last_name="Gómez Ortiz")
    company = ClientFactory(company=True, business_name="Viajes del Norte SAS")

    assert person.display_name == "Marcela Gómez Ortiz"
    assert company.display_name == "Viajes del Norte SAS"


def test_a_new_client_starts_at_version_one_and_each_change_adds_one(session):
    client = ClientFactory()
    assert client.version == 1

    client.city = "Cúcuta"
    session.flush()

    assert client.version == 2


def test_saving_over_a_version_someone_else_already_changed_fails(session):
    client = ClientFactory()
    # Otra petición guardó el mismo cliente entre la lectura y el guardado de esta.
    session.execute(
        text("UPDATE client SET version = version + 1 WHERE id = :id"), {"id": client.id}
    )

    client.city = "Cúcuta"
    with pytest.raises(StaleDataError):
        session.flush()


@pytest.mark.parametrize(
    "overrides, constraint",
    [
        pytest.param({"client_type": "family"}, "ck_client_client_type", id="unknown-type"),
        pytest.param({"first_name": None}, "ck_client_person", id="person-without-first-name"),
        pytest.param({"last_name": None}, "ck_client_person", id="person-without-last-name"),
        pytest.param(
            {"business_name": "Viajes SAS"}, "ck_client_person", id="person-with-business-name"
        ),
        pytest.param(
            {"document_type": "NIT", "document_number": "8001972684"},
            "ck_client_person",
            id="person-with-nit",
        ),
        pytest.param(
            {"document_type": "TI", "document_number": "1098221334"},
            "ck_client_document_type",
            id="document-type-of-travelers-only",
        ),
        pytest.param(
            {"document_type": "CC", "document_number": None},
            "ck_client_document_pair",
            id="type-without-number",
        ),
        pytest.param(
            {"document_type": None, "document_number": "10900001"},
            "ck_client_document_pair",
            id="number-without-type",
        ),
        pytest.param(
            {"contact_source": "tiktok"}, "ck_client_contact_source", id="unknown-source"
        ),
        pytest.param(
            {"contact_source": "other", "contact_source_detail": None},
            "ck_client_contact_source_detail",
            id="other-without-detail",
        ),
    ],
)
def test_the_database_rejects_an_inconsistent_person(session, overrides, constraint):
    with _violates(constraint):
        ClientFactory(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"business_name": None}, id="without-business-name"),
        pytest.param({"first_name": "Ana"}, id="with-first-name"),
        pytest.param({"last_name": "Rojas"}, id="with-last-name"),
        pytest.param({"birth_date": date(1990, 1, 1)}, id="with-birth-date"),
        pytest.param({"document_type": "CC", "document_number": "10900001"}, id="with-cc"),
    ],
)
def test_the_database_rejects_an_inconsistent_company(session, overrides):
    with _violates("ck_client_company"):
        ClientFactory(company=True, **overrides)


def test_a_company_can_have_a_nit(session):
    ClientFactory(company=True, document_type="NIT", document_number="8001972684")


def test_the_client_document_is_unique_per_type(session):
    ClientFactory(document_type="CC", document_number="10900001")

    with _violates("uq_client_document"):
        ClientFactory(document_type="CC", document_number="10900001")


def test_the_same_number_with_another_type_is_another_client(session):
    ClientFactory(document_type="CC", document_number="10900001")

    ClientFactory(document_type="PA", document_number="10900001")


def test_many_clients_can_be_saved_without_a_document(session):
    ClientFactory(document_type=None, document_number=None)
    ClientFactory(document_type=None, document_number=None)


def test_phone_and_email_can_repeat_between_clients(session):
    ClientFactory(phone="+573001112233", email="familia@example.com")

    ClientFactory(phone="+573001112233", email="familia@example.com")


def test_a_traveler_is_saved_with_or_without_a_reference_client(session):
    client = ClientFactory()

    alone = TravelerFactory()
    companion = TravelerFactory(reference_client=client)

    assert alone.reference_client is None
    assert companion.reference_client == client
    assert alone.version == 1


def test_the_traveler_document_is_unique_per_type(session):
    TravelerFactory(document_type="TI", document_number="1098221334")

    with _violates("uq_traveler_document"):
        TravelerFactory(document_type="TI", document_number="1098221334")


def test_a_traveler_cannot_have_a_company_document_type(session):
    with _violates("ck_traveler_document_type"):
        TravelerFactory(document_type="NIT", document_number="8001972684")


def test_being_the_client_needs_a_reference_client(session):
    with _violates("ck_traveler_is_the_client"):
        TravelerFactory(is_the_client=True, reference_client=None)


def test_a_client_has_at_most_one_traveler_that_is_the_client(session):
    client = ClientFactory()
    TravelerFactory(reference_client=client, is_the_client=True)
    TravelerFactory(reference_client=client)

    with _violates("uq_traveler_is_the_client"):
        TravelerFactory(reference_client=client, is_the_client=True)


def test_a_client_with_travelers_cannot_be_deleted(session):
    client = ClientFactory()
    TravelerFactory(reference_client=client)

    session.delete(client)
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    "birth_date, age, is_minor",
    [
        pytest.param(date(2008, 10, 26), 17, True, id="turns-18-tomorrow"),
        pytest.param(date(2008, 10, 25), 18, False, id="turns-18-today"),
    ],
)
def test_the_traveler_age_is_counted_with_the_bogota_date(
    session, monkeypatch, birth_date, age, is_minor
):
    monkeypatch.setattr(models, "today", lambda: date(2026, 10, 25))
    traveler = TravelerFactory(birth_date=birth_date)

    assert (traveler.age, traveler.is_minor) == (age, is_minor)


def test_the_traveler_full_name_joins_names_and_last_names(session):
    traveler = TravelerFactory(first_name="Camila", last_name="Gómez Ortiz")

    assert traveler.full_name == "Camila Gómez Ortiz"
