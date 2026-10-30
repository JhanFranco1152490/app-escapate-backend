from datetime import date

import pytest
from pydantic import ValidationError

from app.clients import schemas
from app.clients.schemas import (
    ClientCreate,
    ClientFilters,
    ClientListItem,
    ClientUpdate,
)

PERSON = {
    "client_type": "person",
    "first_name": "Marcela",
    "last_name": "Gómez Ortiz",
    "document_type": "CC",
    "document_number": "1.020.304.050",
    "birth_date": "1988-06-14",
    "phone": "300 111 2233",
    "email": "Marcela.Gomez@Example.com",
    "city": "Cúcuta",
    "contact_source": "instagram",
    "notes": "Prefiere viajar en diciembre.",
    "data_consent": True,
}

COMPANY = {
    "client_type": "company",
    "business_name": "Viajes del Norte SAS",
    "document_type": "NIT",
    "document_number": "800.197.268-4",
    "phone": "601 234 5678",
    "contact_source": "referral",
    "contact_source_detail": "Recomendado por un cliente",
    "data_consent": True,
}


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(schemas, "today", lambda: date(2026, 10, 25))


def errors_of(model=ClientCreate, base=PERSON, **overrides) -> dict[str, str]:
    """Campo -> mensaje de cada error al validar `base` con los cambios dados."""
    with pytest.raises(ValidationError) as error:
        model(**base | overrides)
    return {item["loc"][-1]: item["msg"] for item in error.value.errors()}


def test_a_person_is_stored_normalized():
    client = ClientCreate(**PERSON)

    assert client.document_number == "1020304050"
    assert client.phone == "+573001112233"
    assert client.email == "marcela.gomez@example.com"
    assert client.birth_date == date(1988, 6, 14)
    assert client.business_name is None


def test_a_company_is_stored_normalized():
    client = ClientCreate(**COMPANY)

    assert client.document_number == "8001972684"
    assert client.phone == "+576012345678"
    assert (client.first_name, client.last_name) == (None, None)


def test_a_client_can_be_registered_without_a_document():
    client = ClientCreate(**PERSON | {"document_type": None, "document_number": None})

    assert (client.document_type, client.document_number) == (None, None)


def test_a_foreign_phone_is_accepted():
    assert ClientCreate(**PERSON | {"phone": "+58 412 555 0101"}).phone == "+584125550101"


@pytest.mark.parametrize("field", ["first_name", "last_name"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_a_person_needs_names(field, value):
    assert errors_of(**{field: value}) == {field: "Este campo es obligatorio."}


@pytest.mark.parametrize("value", [None, "", "   "])
def test_a_company_needs_a_business_name(value):
    assert errors_of(base=COMPANY, business_name=value) == {
        "business_name": "Este campo es obligatorio."
    }


def test_a_person_has_no_business_name():
    assert errors_of(business_name="Viajes SAS") == {
        "business_name": "No aplica para una persona."
    }


@pytest.mark.parametrize(
    "field, value",
    [("first_name", "Ana"), ("last_name", "Rojas"), ("birth_date", "1990-01-01")],
)
def test_a_company_has_no_personal_fields(field, value):
    assert errors_of(base=COMPANY, **{field: value}) == {field: "No aplica para una empresa."}


def test_a_person_does_not_use_a_nit():
    assert errors_of(document_type="NIT", document_number="8001972684") == {
        "document_type": "Una persona se registra con CC, CE, PPT o PA."
    }


@pytest.mark.parametrize("document_type", ["CC", "CE", "PPT", "PA"])
def test_a_company_only_uses_a_nit(document_type):
    assert errors_of(base=COMPANY, document_type=document_type, document_number="10900001") == {
        "document_type": "Una empresa se registra con NIT."
    }


def test_a_document_type_needs_its_number():
    assert errors_of(document_number=None) == {"document_number": "Indica también el número."}


def test_a_document_number_needs_its_type():
    assert errors_of(document_type=None) == {
        "document_number": "Elige también el tipo de documento."
    }


def test_a_nit_with_a_wrong_check_digit_says_so():
    assert errors_of(base=COMPANY, document_number="800.197.268-5") == {
        "document_number": "El dígito de verificación del NIT no coincide."
    }


@pytest.mark.parametrize("number", ["1234", "AB12345", "1" * 31])
def test_an_invalid_document_number_for_its_type(number):
    assert errors_of(document_number=number) == {"document_number": "No es válido para ese tipo."}


@pytest.mark.parametrize("phone", ["12345", "+57 300 111 223", "abc", "3" * 26])
def test_an_invalid_phone(phone):
    assert errors_of(phone=phone) == {"phone": "No es un teléfono válido para ese país."}


def test_other_contact_source_needs_the_detail():
    assert errors_of(contact_source="other") == {"contact_source_detail": "Cuéntanos cuál."}
    assert errors_of(contact_source="other", contact_source_detail="  ") == {
        "contact_source_detail": "Cuéntanos cuál."
    }


def test_a_referral_does_not_need_the_detail():
    assert ClientCreate(**PERSON | {"contact_source": "referral"}).contact_source_detail is None


def test_an_unknown_contact_source_is_rejected():
    assert "contact_source" in errors_of(contact_source="tiktok")


@pytest.mark.parametrize(
    "birth_date, message",
    [
        pytest.param("2026-10-26", "La fecha no puede ser futura.", id="tomorrow"),
        pytest.param("1899-12-31", "Revisa el año.", id="before-1900"),
    ],
)
def test_an_impossible_birth_date(birth_date, message):
    assert errors_of(birth_date=birth_date) == {"birth_date": message}


def test_someone_born_today_is_accepted():
    assert ClientCreate(**PERSON | {"birth_date": "2026-10-25"}).birth_date == date(2026, 10, 25)


@pytest.mark.parametrize(
    "field, length, message",
    [
        ("first_name", 76, "Máximo 75 caracteres."),
        ("city", 81, "Máximo 80 caracteres."),
        ("notes", 2001, "Máximo 2000 caracteres."),
    ],
)
def test_texts_have_a_maximum_length(field, length, message):
    assert errors_of(**{field: "a" * length}) == {field: message}


def test_a_business_name_has_a_maximum_length():
    assert errors_of(base=COMPANY, business_name="a" * 151) == {
        "business_name": "Máximo 150 caracteres."
    }


def test_empty_optional_texts_are_stored_as_none():
    client = ClientCreate(**PERSON | {"city": "  ", "notes": ""})

    assert (client.city, client.notes) == (None, None)


def test_hidden_characters_are_rejected_in_names():
    assert errors_of(first_name="Marce​la") == {
        "first_name": "Contiene caracteres que no se permiten."
    }


@pytest.mark.parametrize("consent", [False, None])
def test_the_data_consent_must_be_confirmed(consent):
    assert errors_of(data_consent=consent) == {
        "data_consent": "Confirma que el cliente autorizó el tratamiento de sus datos."
    }


def test_a_missing_data_consent_is_the_same_error():
    data = {key: value for key, value in PERSON.items() if key != "data_consent"}

    with pytest.raises(ValidationError) as error:
        ClientCreate(**data)

    assert {item["loc"][-1] for item in error.value.errors()} == {"data_consent"}


def test_every_error_is_reported_at_once():
    errors = errors_of(first_name="", phone="123", contact_source="other", data_consent=False)

    assert set(errors) == {"first_name", "phone", "contact_source_detail", "data_consent"}


def test_unknown_fields_are_rejected():
    assert "created_by_id" in errors_of(created_by_id=1)


def test_an_update_needs_the_version_it_read_and_no_consent():
    data = {key: value for key, value in PERSON.items() if key != "data_consent"}

    assert ClientUpdate(**data, expected_version=3).expected_version == 3
    assert "expected_version" in errors_of(ClientUpdate, data, expected_version=0)
    assert "data_consent" in errors_of(ClientUpdate, data, expected_version=1, data_consent=True)


def test_filters_are_trimmed_and_reject_control_characters():
    assert ClientFilters(q="  gomez ").q == "gomez"
    assert ClientFilters(client_type="company").client_type == "company"
    with pytest.raises(ValidationError):
        ClientFilters(q="gomez\x00")
    with pytest.raises(ValidationError):
        ClientFilters(q="a" * 101)


def test_the_list_does_not_carry_the_notes():
    # Las notas pueden traer datos sensibles y la lista no las necesita.
    assert "notes" not in ClientListItem.model_fields
