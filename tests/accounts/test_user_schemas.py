import pytest
from pydantic import ValidationError

from app.accounts.schemas import UserCreate, UserFilters, UserInput

VALID = {
    "first_name": "Laura",
    "last_name": "Rojas",
    "email": "laura.rojas@gmail.com",
    "document_type": "CC",
    "document_number": "1090123456",
    "phone": "3001234567",
}


def errors_of(**overrides) -> dict[str, str]:
    """Campo -> mensaje de cada error al validar `VALID` con los cambios dados."""
    with pytest.raises(ValidationError) as error:
        UserInput(**VALID | overrides)
    return {item["loc"][-1]: item["msg"] for item in error.value.errors()}


def test_valid_data_is_accepted_as_is():
    user = UserInput(**VALID)

    assert user.model_dump() == VALID


def test_values_are_stored_normalized():
    user = UserInput(
        first_name="  Laura  ",
        last_name=" Rojas ",
        email="  Laura.Rojas@GMAIL.com ",
        document_type="CC",
        document_number="1.090.123-456",
        phone="+57 300 123 4567",
    )

    assert (user.first_name, user.last_name) == ("Laura", "Rojas")
    assert user.email == "laura.rojas@gmail.com"
    assert user.document_number == "1090123456"
    assert user.phone == "3001234567"


@pytest.mark.parametrize("field", ["first_name", "last_name"])
@pytest.mark.parametrize("value", ["", "   ", "\n"])
def test_blank_names_are_rejected(field, value):
    assert errors_of(**{field: value}) == {field: "Este campo es obligatorio."}


@pytest.mark.parametrize("field", ["first_name", "last_name"])
def test_names_have_a_maximum_length(field):
    assert errors_of(**{field: "A" * 76}) == {field: "Máximo 75 caracteres."}
    assert UserInput(**VALID | {field: "A" * 75})


@pytest.mark.parametrize(
    "email",
    [
        pytest.param("", id="empty"),
        pytest.param("sin-arroba", id="no-at-sign"),
        pytest.param("a@b", id="no-domain-dot"),
        pytest.param("laura@@gmail.com", id="two-at-signs"),
        pytest.param("Ñandú@gmail.com", id="non-ascii"),
        pytest.param("a" * 250 + "@gmail.com", id="too-long"),
    ],
)
def test_invalid_emails_are_rejected(email):
    assert errors_of(email=email) == {"email": "No es un correo válido."}


@pytest.mark.parametrize(
    "document_type, number",
    [
        pytest.param("CC", "1234", id="cc-too-short"),
        pytest.param("CC", "AB12345", id="cc-with-letters"),
        pytest.param("CC", "١٢٣٤٥٦", id="other-alphabet-digits"),
        pytest.param("CC", "", id="empty"),
        pytest.param("CC", "1" * 31, id="longer-than-allowed"),
        pytest.param("PA", "ÁB12345", id="non-ascii-letter"),
    ],
)
def test_invalid_documents_are_rejected_for_their_type(document_type, number):
    assert errors_of(document_type=document_type, document_number=number) == {
        "document_number": "No es válido para ese tipo."
    }


def test_the_same_number_can_be_valid_for_one_type_and_not_for_another():
    assert UserInput(**VALID | {"document_type": "PA", "document_number": "ab-12345"})
    assert "document_number" in errors_of(document_type="CC", document_number="AB12345")


def test_an_unknown_document_type_is_reported_on_its_own_field_only():
    assert list(errors_of(document_type="NIT")) == ["document_type"]


@pytest.mark.parametrize(
    "phone",
    [
        pytest.param("", id="empty"),
        pytest.param("6012345678", id="landline"),
        pytest.param("300123456", id="too-short"),
        pytest.param("30012345678", id="too-long"),
        pytest.param("300123456A", id="with-letters"),
        pytest.param("3" * 21, id="longer-than-allowed"),
    ],
)
def test_invalid_phones_are_rejected(phone):
    assert errors_of(phone=phone) == {"phone": "Debe ser un celular colombiano de 10 dígitos."}


def test_every_failing_field_is_reported_at_once():
    assert set(errors_of(first_name="", email="x", phone="1")) == {"first_name", "email", "phone"}


@pytest.mark.parametrize("field", list(VALID))
def test_a_missing_field_is_reported(field):
    data = {key: value for key, value in VALID.items() if key != field}

    with pytest.raises(ValidationError) as error:
        UserInput(**data)

    assert [item["loc"][-1] for item in error.value.errors()] == [field]


@pytest.mark.parametrize("extra", ["role_id", "is_active", "password"])
def test_fields_that_are_not_editable_are_rejected(extra):
    with pytest.raises(ValidationError) as error:
        UserInput(**VALID | {extra: 1})

    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_creating_also_requires_a_role():
    assert UserCreate(**VALID | {"role_id": 3}).role_id == 3

    with pytest.raises(ValidationError):
        UserCreate(**VALID)


@pytest.mark.parametrize("role_id", [0, -1, 2**63])
def test_the_role_id_must_fit_the_database(role_id):
    with pytest.raises(ValidationError) as error:
        UserCreate(**VALID | {"role_id": role_id})

    assert [item["loc"][-1] for item in error.value.errors()] == ["role_id"]


@pytest.mark.parametrize("field", ["first_name", "last_name"])
@pytest.mark.parametrize("value", ["Ana\x00", "An\na", "A\tna", "\x07Ana"])
def test_names_cannot_hold_control_characters(field, value):
    assert errors_of(**{field: value}) == {field: "Contiene caracteres que no se permiten."}


def test_the_search_text_cannot_hold_a_nul_character():
    with pytest.raises(ValidationError):
        UserFilters(q="ana\x00")
    assert UserFilters(q="  ana  ").q == "ana"
