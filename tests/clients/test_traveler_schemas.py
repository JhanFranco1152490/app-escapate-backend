from datetime import date

import pytest
from pydantic import ValidationError

from app.clients import schemas
from app.clients.schemas import TravelerCreate, TravelerFilters, TravelerListItem, TravelerUpdate

TRAVELER = {
    "first_name": "Camila",
    "last_name": "Gómez Ortiz",
    "document_type": "TI",
    "document_number": "1.098.221.334",
    "birth_date": "2012-02-03",
    "nationality": " co ",
    "reference_client_id": 5,
    "notes": "Prefiere ventana.",
    "data_consent": True,
}


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(schemas, "today", lambda: date(2026, 10, 25))


def errors_of(model=TravelerCreate, base=TRAVELER, **overrides) -> dict[str, str]:
    with pytest.raises(ValidationError) as error:
        model(**base | overrides)
    return {item["loc"][-1]: item["msg"] for item in error.value.errors()}


def test_a_traveler_is_stored_normalized():
    traveler = TravelerCreate(**TRAVELER)

    assert traveler.document_number == "1098221334"
    assert traveler.nationality == "CO"
    assert traveler.is_the_client is False


def test_a_traveler_does_not_need_a_reference_client():
    assert TravelerCreate(**TRAVELER | {"reference_client_id": None}).reference_client_id is None


@pytest.mark.parametrize("field", ["first_name", "last_name", "document_number"])
def test_texts_are_required(field):
    assert errors_of(**{field: ""})[field]


@pytest.mark.parametrize(
    "field", ["first_name", "last_name", "document_type", "document_number", "birth_date"]
)
def test_missing_required_fields_are_reported(field):
    data = {key: value for key, value in TRAVELER.items() if key != field}

    with pytest.raises(ValidationError) as error:
        TravelerCreate(**data)

    assert field in {item["loc"][-1] for item in error.value.errors()}


@pytest.mark.parametrize(
    "document_type, number",
    [("TI", "109822133"), ("RC", "1234567"), ("CC", "AB12345"), ("PA", "Á1234567")],
)
def test_an_invalid_document_for_its_type(document_type, number):
    assert errors_of(document_type=document_type, document_number=number) == {
        "document_number": "No es válido para ese tipo."
    }


def test_a_traveler_cannot_use_a_nit():
    assert "document_type" in errors_of(document_type="NIT", document_number="8001972684")


def test_an_old_civil_registry_with_letters_is_accepted():
    traveler = TravelerCreate(**TRAVELER | {"document_type": "RC", "document_number": "a1b2c3d4"})

    assert traveler.document_number == "A1B2C3D4"


@pytest.mark.parametrize("nationality", ["XX", "UK", "COL", ""])
def test_the_nationality_must_be_a_country(nationality):
    assert errors_of(nationality=nationality) == {"nationality": "No es un país válido."}


def test_a_missing_nationality_is_reported():
    data = {key: value for key, value in TRAVELER.items() if key != "nationality"}

    with pytest.raises(ValidationError) as error:
        TravelerCreate(**data)

    assert {item["loc"][-1] for item in error.value.errors()} == {"nationality"}


@pytest.mark.parametrize(
    "birth_date, message",
    [
        pytest.param("2026-10-26", "La fecha no puede ser futura.", id="tomorrow"),
        pytest.param("1899-12-31", "Revisa el año.", id="before-1900"),
    ],
)
def test_an_impossible_birth_date(birth_date, message):
    assert errors_of(birth_date=birth_date) == {"birth_date": message}


def test_being_the_client_needs_the_reference_client():
    assert errors_of(is_the_client=True, reference_client_id=None) == {
        "is_the_client": "Elige primero el cliente que también viaja."
    }


def test_the_reference_client_id_must_be_possible():
    assert "reference_client_id" in errors_of(reference_client_id=0)


def test_the_notes_have_a_maximum_length():
    assert errors_of(notes="a" * 1001) == {"notes": "Máximo 1000 caracteres."}


@pytest.mark.parametrize("consent", [False, None])
def test_the_data_consent_must_be_confirmed(consent):
    assert errors_of(data_consent=consent) == {
        "data_consent": (
            "Confirma que el viajero, o su representante legal si es menor de edad, autorizó "
            "el tratamiento de sus datos."
        )
    }


def test_an_update_needs_the_version_it_read_and_no_consent():
    data = {key: value for key, value in TRAVELER.items() if key != "data_consent"}

    assert TravelerUpdate(**data, expected_version=2).expected_version == 2
    assert "expected_version" in errors_of(TravelerUpdate, data, expected_version=0)
    assert "data_consent" in errors_of(TravelerUpdate, data, expected_version=1, data_consent=True)


def test_filters():
    assert TravelerFilters(q=" camila ", client_id=3).model_dump() == {
        "q": "camila",
        "client_id": 3,
    }
    with pytest.raises(ValidationError):
        TravelerFilters(client_id=0)


def test_the_list_does_not_carry_the_notes():
    assert "notes" not in TravelerListItem.model_fields
