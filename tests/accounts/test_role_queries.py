import pytest
from sqlmodel import select

from app.accounts.models import Role, RolePermission
from app.accounts.permissions import PERMISSIONS
from app.accounts.services import role_queries
from app.common.errors import NotFound
from tests.factories import RoleFactory, UserAccountFactory
from tests.statements import recorded_statements

SEEDED = ["Administrador", "Asesor comercial", "Encargado de proveedores", "Operativo"]


def grant(session, role, *codes):
    session.add_all(RolePermission(role_id=role.id, permission=code) for code in codes)
    session.flush()


def test_roles_are_listed_by_name_with_the_seeded_ones(session):
    roles = role_queries.list_roles(session)

    assert [role.name for role in roles if role.name in SEEDED] == SEEDED
    assert {role.id for role in roles} == set(session.exec(select(Role.id)).all())


def test_the_order_ignores_accents_and_case(session):
    for name in ["Zona sur", "Álvaro", "alba", "Bodega"]:
        RoleFactory(name=name)

    names = [role.name for role in role_queries.list_roles(session)]

    mine = [name for name in names if name in {"Zona sur", "Álvaro", "alba", "Bodega"}]
    assert mine == ["alba", "Álvaro", "Bodega", "Zona sur"]


def test_each_role_counts_its_active_and_inactive_accounts(session):
    busy = RoleFactory(name="Con personas")
    empty = RoleFactory(name="Sin personas")
    UserAccountFactory(role=busy)
    UserAccountFactory(role=busy)
    UserAccountFactory(role=busy, is_active=False)

    roles = {role.name: role for role in role_queries.list_roles(session)}

    assert (roles[busy.name].user_count, roles[busy.name].inactive_user_count) == (3, 1)
    assert (roles[empty.name].user_count, roles[empty.name].inactive_user_count) == (0, 0)


def test_the_list_describes_each_role(session):
    roles = {role.name: role for role in role_queries.list_roles(session)}

    assert roles["Administrador"].is_protected is True
    assert roles["Operativo"].is_protected is False
    assert roles["Operativo"].description == "Reservas, documentos y pagos posteriores a la venta."


def test_the_list_is_a_single_query(session):
    for _ in range(3):
        UserAccountFactory(role=RoleFactory())
    session.expire_all()
    with recorded_statements(session) as statements:
        role_queries.list_roles(session)

    assert len(statements) == 1


def test_a_role_detail_has_its_permissions_in_alphabetical_order(session):
    role = RoleFactory(description="Atiende a los clientes.")
    grant(session, role, "users.view", "roles.view", "roles.manage")
    UserAccountFactory(role=role, is_active=False)

    detail = role_queries.get_role(session, role.id)

    assert detail.permissions == ["roles.manage", "roles.view", "users.view"]
    assert (detail.name, detail.description) == (role.name, "Atiende a los clientes.")
    assert (detail.user_count, detail.inactive_user_count) == (1, 1)
    assert detail.created_at and detail.updated_at


def test_a_permission_outside_the_registry_is_not_shown(session):
    role = RoleFactory()
    grant(session, role, "users.view", "retired.permission")

    assert role_queries.get_role(session, role.id).permissions == ["users.view"]
    assert role_queries.registered_permissions_of(session, role.id) == {"users.view"}


def test_an_unknown_role_is_not_found(session):
    with pytest.raises(NotFound):
        role_queries.get_role(session, 999_999_999)


def test_the_catalog_lists_the_whole_registry_in_order(session):
    catalog = role_queries.permission_catalog()

    assert [item.code for item in catalog] == list(PERMISSIONS)


def test_each_catalog_item_carries_its_place_in_the_matrix(session):
    item = next(item for item in role_queries.permission_catalog() if item.code == "users.manage")

    assert (item.section, item.group, item.label) == ("Administración", "Usuarios", "Gestionar")
    assert item.description == "Gestionar usuarios"
    assert item.requires == ["users.view"]
    assert item.help == PERMISSIONS["users.manage"].help
