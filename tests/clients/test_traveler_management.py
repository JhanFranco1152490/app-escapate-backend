import pytest

from app.clients.errors import ClientAlreadyTraveler, DuplicateTraveler, InvalidReferenceClient
from app.clients.schemas import TravelerCreate, TravelerUpdate
from app.clients.services import traveler_management
from app.common.errors import InvalidFields, NotFound, StaleVersion
from tests.factories import ClientFactory, UserAccountFactory

TRAVELER = {
    "first_name": "Camila",
    "last_name": "Gómez Ortiz",
    "document_type": "TI",
    "document_number": "1.098.221.334",
    "birth_date": "2012-02-03",
    "nationality": "CO",
}


@pytest.fixture
def advisor(session):
    return UserAccountFactory()


def create(session, actor, **data):
    return traveler_management.create_traveler(
        session, actor, TravelerCreate(**TRAVELER | data, data_consent=True)
    )


def update(session, traveler, **changes):
    current = {
        "first_name": traveler.first_name,
        "last_name": traveler.last_name,
        "document_type": traveler.document_type,
        "document_number": traveler.document_number,
        "birth_date": traveler.birth_date,
        "nationality": traveler.nationality,
        "reference_client_id": traveler.reference_client_id,
        "is_the_client": traveler.is_the_client,
        "notes": traveler.notes,
        "expected_version": traveler.version,
    }
    return traveler_management.update_traveler(
        session, traveler.id, TravelerUpdate(**current | changes)
    )


def test_a_traveler_is_registered_without_a_reference_client(session, advisor):
    traveler = create(session, advisor)

    assert traveler.document_number == "1098221334"
    assert traveler.reference_client is None
    assert (traveler.created_by_id, traveler.data_consent_by_id) == (advisor.id, advisor.id)
    assert traveler.version == 1


def test_a_client_can_have_several_travelers(session, advisor):
    client = ClientFactory()

    first = create(session, advisor, reference_client_id=client.id)
    second = create(session, advisor, reference_client_id=client.id, document_number="1098221335")

    assert first.reference_client == second.reference_client == client


def test_the_client_can_also_be_a_traveler(session, advisor):
    client = ClientFactory()

    traveler = create(session, advisor, reference_client_id=client.id, is_the_client=True)

    assert traveler.is_the_client


def test_an_unknown_reference_client_is_rejected(session, advisor):
    with pytest.raises(InvalidReferenceClient) as error:
        create(session, advisor, reference_client_id=999_999_999)

    assert error.value.fields == {"reference_client_id": ["Elige un cliente registrado."]}


def test_a_company_cannot_also_be_a_traveler(session, advisor):
    company = ClientFactory(company=True)

    with pytest.raises(InvalidReferenceClient) as error:
        create(session, advisor, reference_client_id=company.id, is_the_client=True)

    assert error.value.fields == {
        "reference_client_id": ["Solo una persona puede ser también viajero."]
    }


def test_a_company_can_be_the_reference_client_of_its_employees(session, advisor):
    company = ClientFactory(company=True)

    assert create(session, advisor, reference_client_id=company.id).reference_client == company


def test_a_client_has_only_one_traveler_that_is_itself(session, advisor):
    client = ClientFactory()
    create(session, advisor, reference_client_id=client.id, is_the_client=True)

    with pytest.raises(ClientAlreadyTraveler):
        create(
            session,
            advisor,
            reference_client_id=client.id,
            is_the_client=True,
            document_number="1098221335",
        )


def test_a_repeated_document_is_rejected(session, advisor):
    create(session, advisor)

    with pytest.raises(DuplicateTraveler):
        create(session, advisor, document_number="1098221334")


def test_every_problem_is_reported_at_once(session, advisor):
    create(session, advisor)

    with pytest.raises(InvalidFields) as error:
        create(session, advisor, reference_client_id=999_999_999)

    assert set(error.value.fields) == {"document_number", "reference_client_id"}


@pytest.mark.parametrize("constraint_check", ["_ensure_document_is_free", "_check_reference"])
def test_the_database_constraint_gives_the_same_error_when_the_check_is_skipped(
    session, advisor, monkeypatch, constraint_check
):
    client = ClientFactory()
    create(session, advisor, reference_client_id=client.id, is_the_client=True)
    monkeypatch.setattr(traveler_management, constraint_check, lambda *args, **kwargs: [])

    data = {"reference_client_id": client.id, "is_the_client": True}
    if constraint_check == "_check_reference":
        data["document_number"] = "1098221335"
        expected = ClientAlreadyTraveler
    else:
        data["is_the_client"] = False
        expected = DuplicateTraveler

    with pytest.raises(expected) as error:
        create(session, advisor, **data)

    assert error.value.__cause__ is None and error.value.__suppress_context__


def test_editing_keeps_the_new_data_and_adds_a_version(session, advisor):
    traveler = create(session, advisor)

    edited = update(session, traveler, notes="Ventana", nationality="VE")

    assert (edited.notes, edited.nationality, edited.version) == ("Ventana", "VE", 2)


def test_the_reference_client_can_be_removed(session, advisor):
    traveler = create(session, advisor, reference_client_id=ClientFactory().id)

    assert update(session, traveler, reference_client_id=None).reference_client is None


def test_its_own_mark_and_document_are_not_duplicates(session, advisor):
    client = ClientFactory()
    traveler = create(session, advisor, reference_client_id=client.id, is_the_client=True)

    update(session, traveler, notes="Sin cambios en el documento")


def test_editing_over_an_old_version_is_rejected(session, advisor):
    traveler = create(session, advisor)
    update(session, traveler, notes="Primera")

    with pytest.raises(StaleVersion):
        update(session, traveler, notes="Segunda", expected_version=1)


def test_editing_an_unknown_traveler_is_not_found(session):
    with pytest.raises(NotFound):
        traveler_management.update_traveler(
            session, 999_999_999, TravelerUpdate(**TRAVELER, expected_version=1)
        )
