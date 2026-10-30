from sqlmodel import select

from app.accounts.models import Role, RolePermission
from app.accounts.permissions import PERMISSIONS

CLIENT_PERMISSIONS = {"clients.view", "clients.manage", "travelers.view", "travelers.manage"}


def _granted(session, role_name: str) -> set[str]:
    statement = (
        select(RolePermission.permission)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name == role_name)
    )
    return set(session.exec(statement)) & CLIENT_PERMISSIONS


def test_the_permissions_are_in_the_commercial_section():
    assert {PERMISSIONS[code].section for code in CLIENT_PERMISSIONS} == {"Comercial"}
    assert PERMISSIONS["clients.manage"].group == "Clientes"
    assert PERMISSIONS["travelers.manage"].group == "Viajeros"


def test_managing_requires_viewing():
    assert PERMISSIONS["clients.manage"].requires == ("clients.view",)
    assert PERMISSIONS["travelers.manage"].requires == ("travelers.view",)
    assert PERMISSIONS["clients.view"].requires == ()
    assert PERMISSIONS["travelers.view"].requires == ()


def test_the_commercial_advisor_gets_all_four(session):
    assert _granted(session, "Asesor comercial") == CLIENT_PERMISSIONS


def test_the_operations_role_can_only_view(session):
    assert _granted(session, "Operativo") == {"clients.view", "travelers.view"}


def test_the_supplier_manager_gets_none(session):
    assert _granted(session, "Encargado de proveedores") == set()
