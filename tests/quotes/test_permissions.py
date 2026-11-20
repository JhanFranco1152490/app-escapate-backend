from sqlmodel import select

from app.accounts.models import Role, RolePermission
from app.accounts.permissions import PERMISSIONS

QUOTE_PERMISSIONS = {"quotes.view", "quotes.manage"}


def _granted(session, role_name: str) -> set[str]:
    statement = (
        select(RolePermission.permission)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name == role_name)
    )
    return set(session.exec(statement)) & QUOTE_PERMISSIONS


def test_the_permissions_are_in_the_commercial_section():
    assert {PERMISSIONS[code].section for code in QUOTE_PERMISSIONS} == {"Comercial"}
    assert {PERMISSIONS[code].group for code in QUOTE_PERMISSIONS} == {"Cotizaciones"}


def test_managing_requires_viewing():
    assert PERMISSIONS["quotes.manage"].requires == ("quotes.view",)


def test_the_commercial_advisor_gets_both(session):
    assert _granted(session, "Asesor comercial") == QUOTE_PERMISSIONS


def test_the_operations_role_can_only_view(session):
    assert _granted(session, "Operativo") == {"quotes.view"}


def test_the_supplier_manager_gets_none(session):
    assert _granted(session, "Encargado de proveedores") == set()
