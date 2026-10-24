import pytest
from pydantic import ValidationError

from app.accounts.schemas import PermissionItem, RoleInput, UserRoleInput

VALID = {
    "name": "Ventas",
    "description": "Atiende a los clientes nuevos.",
    "permissions": ["users.view"],
}


def errors_of(**overrides) -> dict[str, str]:
    """Campo -> mensaje de cada error al validar `VALID` con los cambios dados."""
    with pytest.raises(ValidationError) as error:
        RoleInput(**VALID | overrides)
    return {item["loc"][0]: item["msg"] for item in error.value.errors()}


def test_valid_data_is_accepted_as_is():
    assert RoleInput(**VALID).model_dump() == VALID


def test_name_and_description_are_trimmed():
    role = RoleInput(**VALID | {"name": "  Ventas ", "description": "  Atiende.  "})

    assert (role.name, role.description) == ("Ventas", "Atiende.")


@pytest.mark.parametrize("description", ["", "   ", None])
def test_an_empty_description_is_stored_as_none(description):
    assert RoleInput(**VALID | {"description": description}).description is None


def test_description_is_optional():
    data = {key: value for key, value in VALID.items() if key != "description"}

    assert RoleInput(**data).description is None


@pytest.mark.parametrize("name", ["", "   "])
def test_name_is_required(name):
    assert errors_of(name=name) == {"name": "Este campo es obligatorio."}


def test_name_has_at_most_80_characters():
    assert RoleInput(**VALID | {"name": "a" * 80}).name == "a" * 80
    assert errors_of(name="a" * 81) == {"name": "Máximo 80 caracteres."}


def test_description_has_at_most_200_characters():
    assert errors_of(description="a" * 201) == {"description": "Máximo 200 caracteres."}


@pytest.mark.parametrize("hidden", ["\x00", "​", "﻿"])
@pytest.mark.parametrize("field", ["name", "description"])
def test_control_and_invisible_characters_are_rejected(field, hidden):
    errors = errors_of(**{field: f"Ven{hidden}tas"})

    assert errors == {field: "Contiene caracteres que no se permiten."}


def test_permissions_are_required():
    data = {key: value for key, value in VALID.items() if key != "permissions"}

    with pytest.raises(ValidationError):
        RoleInput(**data)


def test_a_role_can_have_no_permissions():
    assert RoleInput(**VALID | {"permissions": []}).permissions == []


def test_at_most_100_permission_codes():
    assert "permissions" in errors_of(permissions=["users.view"] * 101)


def test_a_permission_code_has_at_most_100_characters():
    assert "permissions" in errors_of(permissions=["a" * 101])


def test_unknown_codes_are_left_for_the_service():
    # Que el código exista lo revisa el servicio: necesita el registro y sus descripciones.
    assert RoleInput(**VALID | {"permissions": ["users.fly"]}).permissions == ["users.fly"]


@pytest.mark.parametrize("extra", ["is_protected", "id"])
def test_extra_fields_are_rejected(extra):
    assert extra in errors_of(**{extra: True})


@pytest.mark.parametrize("role_id", [0, -1, 2**63])
def test_user_role_input_needs_a_possible_id(role_id):
    with pytest.raises(ValidationError):
        UserRoleInput(role_id=role_id)


def test_user_role_input_rejects_extra_fields():
    with pytest.raises(ValidationError):
        UserRoleInput(role_id=1, user_id=2)


def test_permission_item_carries_its_place_in_the_matrix():
    item = PermissionItem(
        code="users.manage",
        section="Administración",
        group="Usuarios",
        label="Gestionar",
        description="Gestionar usuarios",
        requires=["users.view"],
        help=None,
    )

    assert item.requires == ["users.view"]
