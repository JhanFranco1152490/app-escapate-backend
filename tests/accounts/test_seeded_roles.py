"""Lo que las migraciones dejan en los roles sembrados.

Estas pruebas vigilan también las migraciones de dominios futuros: cada permiso nuevo del
registro tiene que llegar al rol protegido, y ningún par de roles sembrados puede quedar
autorizando exactamente lo mismo.
"""

from itertools import combinations

from sqlmodel import select

from app.accounts.models import Role, RolePermission
from app.accounts.permissions import PERMISSIONS

DESCRIPTIONS = {
    "Administrador": "Acceso a todo el panel, incluida la gestión de usuarios y permisos.",
    "Asesor comercial": "Clientes, viajeros, solicitudes y borradores.",
    "Encargado de proveedores": "Proveedores, servicios y tarifas.",
    "Operativo": "Reservas, documentos y pagos posteriores a la venta.",
}


def _registered_permissions(session, role_id: int) -> frozenset[str]:
    statement = select(RolePermission.permission).where(RolePermission.role_id == role_id)
    return frozenset(code for code in session.exec(statement) if code in PERMISSIONS)


def test_the_administrator_is_the_only_protected_role(session):
    protected = session.exec(select(Role).where(Role.is_protected)).all()

    assert [role.name for role in protected] == ["Administrador"]


def test_the_protected_role_has_every_registered_permission(session):
    protected = session.exec(select(Role).where(Role.is_protected)).one()

    assert _registered_permissions(session, protected.id) == frozenset(PERMISSIONS)


def test_no_two_seeded_roles_grant_the_same_permissions(session):
    roles = session.exec(select(Role)).all()
    grants = {role.name: _registered_permissions(session, role.id) for role in roles}

    repeated = [
        (first, second)
        for first, second in combinations(grants, 2)
        if grants[first] and grants[first] == grants[second]
    ]
    assert repeated == []


def test_the_seeded_roles_are_described(session):
    roles = session.exec(select(Role).where(Role.name.in_(DESCRIPTIONS))).all()

    assert {role.name: role.description for role in roles} == DESCRIPTIONS
