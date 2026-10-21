import pytest
from sqlmodel import select

from app.accounts.errors import (
    CannotEditOwnRole,
    InvalidFields,
    LastUserManager,
    RoleInUse,
    RoleProtected,
)
from app.accounts.models import Role, RolePermission
from app.accounts.permissions import PERMISSIONS
from app.accounts.schemas import RoleInput
from app.accounts.services import role_management
from app.accounts.services.role_queries import registered_permissions_of
from app.common.errors import NotFound
from tests.factories import RoleFactory, UserAccountFactory


def role_input(name="Ventas", description=None, permissions=()):
    return RoleInput(name=name, description=description, permissions=list(permissions))


def grant(session, role, *codes):
    session.add_all(RolePermission(role_id=role.id, permission=code) for code in codes)
    session.flush()


def stored_codes(session, role_id) -> set[str]:
    statement = select(RolePermission.permission).where(RolePermission.role_id == role_id)
    return set(session.exec(statement).all())


@pytest.fixture
def actor(session, advisor_role):
    # Sin roles.manage: el servicio no depende de que el endpoint revise el permiso.
    return UserAccountFactory(role=advisor_role)


# --- Crear ---------------------------------------------------------------------------------


def test_creating_a_role_stores_it_with_its_permissions(session):
    detail = role_management.create_role(
        session, role_input(description="Atiende clientes.", permissions=["users.view"])
    )

    role = session.get(Role, detail.id)
    assert (role.name, role.description, role.is_protected) == (
        "Ventas",
        "Atiende clientes.",
        False,
    )
    assert stored_codes(session, role.id) == {"users.view"}
    assert detail.permissions == ["users.view"]
    assert (detail.user_count, detail.inactive_user_count) == (0, 0)


def test_a_role_can_be_created_without_permissions(session):
    detail = role_management.create_role(session, role_input())

    assert detail.permissions == []


def test_repeated_codes_are_stored_once(session):
    detail = role_management.create_role(
        session, role_input(permissions=["users.view", "users.view"])
    )

    assert stored_codes(session, detail.id) == {"users.view"}


def test_an_unknown_permission_is_rejected(session):
    with pytest.raises(InvalidFields) as error:
        role_management.create_role(session, role_input(permissions=["users.fly"]))

    assert error.value.fields == {"permissions": ["Permiso desconocido: users.fly."]}


def test_a_permission_without_what_it_requires_is_rejected(session):
    with pytest.raises(InvalidFields) as error:
        role_management.create_role(
            session, role_input(permissions=["users.manage", "roles.manage"])
        )

    assert error.value.fields == {
        "permissions": [
            "Gestionar usuarios necesita Ver usuarios.",
            "Gestionar roles y permisos necesita Ver roles y permisos.",
        ]
    }


def test_a_name_taken_with_other_case_is_rejected(session):
    RoleFactory(name="Ventas")

    with pytest.raises(InvalidFields) as error:
        role_management.create_role(session, role_input(name="VENTAS"))

    assert error.value.fields == {"name": ["Ya existe un rol con ese nombre."]}


# --- Sin roles repetidos -------------------------------------------------------------------


def test_the_same_permissions_as_another_role_are_rejected(session):
    grant(session, RoleFactory(name="Consulta"), "users.view", "roles.view")

    with pytest.raises(InvalidFields) as error:
        role_management.create_role(
            session, role_input(permissions=["roles.view", "users.view", "roles.view"])
        )

    assert error.value.fields == {
        "permissions": ["El rol Consulta ya tiene exactamente estos permisos."]
    }


def test_every_permission_matches_the_administrator(session):
    with pytest.raises(InvalidFields) as error:
        role_management.create_role(session, role_input(permissions=list(PERMISSIONS)))

    assert error.value.fields == {
        "permissions": ["El rol Administrador ya tiene exactamente estos permisos."]
    }


def test_several_roles_can_have_no_permissions(session):
    role_management.create_role(session, role_input(name="Primero"))
    role_management.create_role(session, role_input(name="Segundo"))


def test_a_retired_permission_does_not_make_two_roles_different(session):
    grant(session, RoleFactory(name="Antiguo"), "users.view", "retired.permission")

    with pytest.raises(InvalidFields) as error:
        role_management.create_role(session, role_input(permissions=["users.view"]))

    assert error.value.fields == {
        "permissions": ["El rol Antiguo ya tiene exactamente estos permisos."]
    }


def test_editing_a_role_into_the_permissions_of_another_is_rejected(session, actor):
    grant(session, RoleFactory(name="Consulta"), "users.view")
    role = RoleFactory(name="Ventas")

    with pytest.raises(InvalidFields):
        role_management.update_role(
            session, actor, role.id, role_input(permissions=["users.view"])
        )

    assert stored_codes(session, role.id) == set()


def test_renaming_a_role_that_already_matches_another_is_allowed(session, actor):
    grant(session, RoleFactory(name="Consulta"), "users.view")
    twin = RoleFactory(name="Copia")
    grant(session, twin, "users.view")

    detail = role_management.update_role(
        session, actor, twin.id, role_input(name="Consulta interna", permissions=["users.view"])
    )

    assert detail.name == "Consulta interna"


# --- Editar --------------------------------------------------------------------------------


def test_editing_changes_name_description_and_permissions(session, actor):
    role = RoleFactory(name="Ventas")
    grant(session, role, "users.view", "retired.permission")

    detail = role_management.update_role(
        session,
        actor,
        role.id,
        role_input(name="Ventas", description="Nueva.", permissions=["roles.view"]),
    )

    assert (detail.name, detail.description, detail.permissions) == (
        "Ventas",
        "Nueva.",
        ["roles.view"],
    )
    assert stored_codes(session, role.id) == {"roles.view"}


def test_changing_only_the_case_of_its_own_name_is_allowed(session, actor):
    role = RoleFactory(name="ventas")

    assert role_management.update_role(session, actor, role.id, role_input()).name == "Ventas"


def test_another_role_name_is_rejected_when_editing(session, actor):
    RoleFactory(name="Ventas")
    role = RoleFactory(name="Bodega")

    with pytest.raises(InvalidFields) as error:
        role_management.update_role(session, actor, role.id, role_input(name="ventas"))

    assert error.value.fields == {"name": ["Ya existe un rol con ese nombre."]}


def test_the_protected_role_description_can_be_edited(session, actor, administrator_role):
    detail = role_management.update_role(
        session,
        actor,
        administrator_role.id,
        role_input(name="Administrador", description="Dueños.", permissions=list(PERMISSIONS)),
    )

    assert detail.description == "Dueños."


@pytest.mark.parametrize(
    "change",
    [
        {"name": "Dirección", "permissions": list(PERMISSIONS)},
        {"name": "Administrador", "permissions": ["users.view"]},
    ],
)
def test_the_protected_role_name_and_permissions_cannot_change(
    session, actor, administrator_role, change
):
    with pytest.raises(RoleProtected):
        role_management.update_role(session, actor, administrator_role.id, role_input(**change))

    session.refresh(administrator_role)
    assert administrator_role.name == "Administrador"
    assert registered_permissions_of(session, administrator_role.id) == frozenset(PERMISSIONS)


def test_nobody_changes_the_permissions_of_their_own_role(session):
    role = RoleFactory(name="Gerencia")
    grant(session, role, "roles.view", "roles.manage")
    actor = UserAccountFactory(role=role)

    with pytest.raises(CannotEditOwnRole):
        role_management.update_role(
            session, actor, role.id, role_input(name="Gerencia", permissions=["roles.view"])
        )


def test_renaming_or_describing_their_own_role_is_allowed(session):
    role = RoleFactory(name="Gerencia")
    grant(session, role, "roles.view", "roles.manage")
    actor = UserAccountFactory(role=role)

    detail = role_management.update_role(
        session,
        actor,
        role.id,
        role_input(
            name="Dirección", description="Otra.", permissions=["roles.manage", "roles.view"]
        ),
    )

    assert (detail.name, detail.description) == ("Dirección", "Otra.")


def test_removing_manage_users_from_the_last_managers_role_is_rejected(session, actor):
    role = RoleFactory(name="Gerencia")
    grant(session, role, "users.view", "users.manage")
    UserAccountFactory(role=role)

    with pytest.raises(LastUserManager):
        role_management.update_role(
            session, actor, role.id, role_input(name="Gerencia", permissions=["users.view"])
        )

    assert "users.manage" in stored_codes(session, role.id)


def test_removing_manage_users_is_allowed_while_an_administrator_is_active(
    session, actor, administrator_role
):
    role = RoleFactory(name="Gerencia")
    grant(session, role, "users.view", "users.manage")
    UserAccountFactory(role=role)
    UserAccountFactory(role=administrator_role)

    detail = role_management.update_role(
        session, actor, role.id, role_input(name="Gerencia", permissions=["users.view"])
    )

    assert detail.permissions == ["users.view"]


def test_editing_an_unknown_role_is_not_found(session, actor):
    with pytest.raises(NotFound):
        role_management.update_role(session, actor, 999_999_999, role_input())


# --- Borrar --------------------------------------------------------------------------------


def test_deleting_a_role_without_accounts_removes_it_and_its_permissions(session):
    role = RoleFactory()
    grant(session, role, "users.view")
    role_id = role.id

    role_management.delete_role(session, role_id)

    session.expire_all()
    assert session.get(Role, role_id) is None
    assert stored_codes(session, role_id) == set()


def test_a_role_with_an_inactive_account_cannot_be_deleted(session):
    role = RoleFactory()
    UserAccountFactory(role=role, is_active=False)

    with pytest.raises(RoleInUse):
        role_management.delete_role(session, role.id)


def test_the_protected_role_cannot_be_deleted(session, administrator_role):
    with pytest.raises(RoleProtected):
        role_management.delete_role(session, administrator_role.id)


def test_deleting_an_unknown_role_is_not_found(session):
    with pytest.raises(NotFound):
        role_management.delete_role(session, 999_999_999)
