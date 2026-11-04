from sqlmodel import select

from app.accounts.models import Role, RolePermission
from app.accounts.permissions import PERMISSIONS

SUPPLIER_PERMISSIONS = {"suppliers.view", "suppliers.manage"}


def _granted(session, role_name: str) -> set[str]:
    statement = (
        select(RolePermission.permission)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name == role_name)
    )
    return set(session.exec(statement)) & SUPPLIER_PERMISSIONS


def test_the_permissions_are_in_the_tourism_offer_section():
    assert {PERMISSIONS[code].section for code in SUPPLIER_PERMISSIONS} == {"Oferta turística"}
    assert {PERMISSIONS[code].group for code in SUPPLIER_PERMISSIONS} == {"Proveedores"}


def test_the_section_comes_after_the_commercial_one():
    codes = list(PERMISSIONS)

    assert codes.index("suppliers.view") > codes.index("travelers.manage")


def test_managing_requires_viewing():
    assert PERMISSIONS["suppliers.manage"].requires == ("suppliers.view",)
    assert PERMISSIONS["suppliers.view"].requires == ()


def test_the_supplier_manager_gets_both(session):
    assert _granted(session, "Encargado de proveedores") == SUPPLIER_PERMISSIONS


def test_the_administrator_gets_both(session):
    assert _granted(session, "Administrador") == SUPPLIER_PERMISSIONS


def test_the_commercial_advisor_and_the_operations_role_can_only_view(session):
    assert _granted(session, "Asesor comercial") == {"suppliers.view"}
    assert _granted(session, "Operativo") == {"suppliers.view"}
