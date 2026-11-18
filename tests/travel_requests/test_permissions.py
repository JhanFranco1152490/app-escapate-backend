from sqlmodel import select

from app.accounts.models import Role, RolePermission
from app.accounts.permissions import PERMISSIONS

REQUEST_PERMISSIONS = {"travel_requests.view", "travel_requests.manage"}


def _granted(session, role_name: str) -> set[str]:
    statement = (
        select(RolePermission.permission)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name == role_name)
    )
    return set(session.exec(statement)) & REQUEST_PERMISSIONS


def test_the_permissions_are_in_the_commercial_section():
    assert {PERMISSIONS[code].section for code in REQUEST_PERMISSIONS} == {"Comercial"}
    assert {PERMISSIONS[code].group for code in REQUEST_PERMISSIONS} == {"Solicitudes"}


def test_managing_requires_viewing():
    assert PERMISSIONS["travel_requests.manage"].requires == ("travel_requests.view",)
    assert PERMISSIONS["travel_requests.view"].requires == ()


def test_the_protected_role_gets_both(session):
    statement = (
        select(RolePermission.permission)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.is_protected)
    )
    assert set(session.exec(statement)) >= REQUEST_PERMISSIONS


def test_the_commercial_advisor_gets_both(session):
    assert _granted(session, "Asesor comercial") == REQUEST_PERMISSIONS


def test_the_operations_role_can_only_view(session):
    assert _granted(session, "Operativo") == {"travel_requests.view"}


def test_the_supplier_manager_gets_none(session):
    assert _granted(session, "Encargado de proveedores") == set()
