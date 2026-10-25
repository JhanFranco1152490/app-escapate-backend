import pytest
from sqlalchemy import text

from app.clients.errors import ClientTypeChanged, DuplicateClient
from app.clients.schemas import ClientCreate, ClientUpdate
from app.clients.services import client_management
from app.common.errors import NotFound, StaleVersion
from tests.factories import ClientFactory, TravelerFactory, UserAccountFactory

PERSON = {
    "client_type": "person",
    "first_name": "Marcela",
    "last_name": "Gómez Ortiz",
    "document_type": "CC",
    "document_number": "1.020.304.050",
    "phone": "300 111 2233",
    "email": "marcela.gomez@example.com",
    "contact_source": "instagram",
}
COMPANY = {
    "client_type": "company",
    "business_name": "Viajes del Norte SAS",
    "document_type": "NIT",
    "document_number": "800.197.268-4",
    "phone": "601 234 5678",
    "contact_source": "other",
    "contact_source_detail": "Feria de turismo",
}


@pytest.fixture
def advisor(session):
    return UserAccountFactory(first_name="Laura", last_name="Rojas")


def create(session, actor, **data):
    return client_management.create_client(session, actor, ClientCreate(**data, data_consent=True))


def update(session, client, **changes):
    current = {
        "client_type": client.client_type,
        "first_name": client.first_name,
        "last_name": client.last_name,
        "business_name": client.business_name,
        "document_type": client.document_type,
        "document_number": client.document_number,
        "birth_date": client.birth_date,
        "phone": client.phone,
        "email": client.email,
        "city": client.city,
        "contact_source": client.contact_source,
        "contact_source_detail": client.contact_source_detail,
        "notes": client.notes,
        "expected_version": client.version,
    }
    return client_management.update_client(session, client.id, ClientUpdate(**current | changes))


def test_a_person_is_registered_with_who_registered_it_and_the_consent(session, advisor):
    client = create(session, advisor, **PERSON)

    assert client.id is not None
    assert client.display_name == "Marcela Gómez Ortiz"
    assert (client.document_number, client.phone) == ("1020304050", "+573001112233")
    assert client.created_by.full_name == "Laura Rojas"
    assert client.data_consent_by_id == advisor.id
    assert client.data_consent_at is not None
    assert client.version == 1


def test_a_company_is_registered(session, advisor):
    client = create(session, advisor, **COMPANY)

    assert (client.display_name, client.document_number) == ("Viajes del Norte SAS", "8001972684")


def test_two_clients_can_be_registered_without_a_document(session, advisor):
    without_document = PERSON | {"document_type": None, "document_number": None}

    first = create(session, advisor, **without_document)
    second = create(session, advisor, **without_document)

    assert first.id != second.id


def test_a_repeated_document_written_another_way_is_rejected(session, advisor):
    create(session, advisor, **PERSON)

    with pytest.raises(DuplicateClient):
        create(session, advisor, **PERSON | {"document_number": "1020304050"})


def test_the_same_number_with_another_type_is_another_client(session, advisor):
    create(session, advisor, **PERSON)

    create(session, advisor, **PERSON | {"document_type": "PA"})


def test_a_repeated_phone_and_email_are_accepted(session, advisor):
    create(session, advisor, **PERSON)

    create(session, advisor, **PERSON | {"document_number": "80112233"})


def test_the_database_constraint_gives_the_same_error_when_the_check_is_skipped(
    session, advisor, monkeypatch
):
    create(session, advisor, **PERSON)
    # Como si otra petición hubiera guardado el mismo documento después de la revisión.
    monkeypatch.setattr(client_management, "_ensure_document_is_free", lambda *args: None)

    with pytest.raises(DuplicateClient) as error:
        create(session, advisor, **PERSON)

    # El error de la base trae el documento: no se encadena.
    assert error.value.__cause__ is None and error.value.__suppress_context__


def test_editing_keeps_the_new_data_and_adds_a_version(session, advisor):
    client = create(session, advisor, **PERSON)

    edited = update(session, client, city="Cúcuta", phone="+58 412 555 0101")

    assert (edited.city, edited.phone, edited.version) == ("Cúcuta", "+584125550101", 2)
    assert edited.created_by_id == advisor.id


def test_editing_does_not_touch_the_consent(session, advisor):
    client = create(session, advisor, **PERSON)
    recorded = (client.data_consent_at, client.data_consent_by_id)

    edited = update(session, client, city="Cúcuta")

    assert (edited.data_consent_at, edited.data_consent_by_id) == recorded


def test_its_own_document_is_not_a_duplicate(session, advisor):
    client = create(session, advisor, **PERSON)

    update(session, client, document_number="1.020.304.050")


def test_another_clients_document_is_a_duplicate(session, advisor):
    create(session, advisor, **PERSON)
    other = create(session, advisor, **PERSON | {"document_number": "80112233"})

    with pytest.raises(DuplicateClient):
        update(session, other, document_number="1020304050")


def test_the_client_type_cannot_change(session, advisor):
    client = create(session, advisor, **PERSON)

    with pytest.raises(ClientTypeChanged):
        update(
            session,
            client,
            client_type="company",
            first_name=None,
            last_name=None,
            business_name="Gómez SAS",
            document_type=None,
            document_number=None,
        )


def test_editing_over_an_old_version_is_rejected(session, advisor):
    client = create(session, advisor, **PERSON)
    update(session, client, city="Cúcuta")

    with pytest.raises(StaleVersion):
        update(session, client, city="Bogotá", expected_version=1)


def test_editing_an_unknown_client_is_not_found(session):
    with pytest.raises(NotFound):
        client_management.update_client(
            session, 999_999_999, ClientUpdate(**PERSON, expected_version=1)
        )


def test_editing_the_client_does_not_change_its_traveler(session, advisor):
    client = create(session, advisor, **PERSON)
    traveler = TravelerFactory(
        reference_client=client, is_the_client=True, first_name="Marcela", last_name="Gómez"
    )

    update(session, client, first_name="Marcela Andrea")
    session.refresh(traveler)

    assert traveler.first_name == "Marcela"


def test_an_error_after_the_check_leaves_nothing_saved(session, advisor):
    ClientFactory(document_type="CC", document_number="1020304050")
    before = session.execute(text("SELECT count(*) FROM client")).scalar_one()

    with pytest.raises(DuplicateClient):
        create(session, advisor, **PERSON)

    assert session.execute(text("SELECT count(*) FROM client")).scalar_one() == before
