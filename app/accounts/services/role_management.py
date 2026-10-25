"""Gestión de roles: crear, editar y borrar.

Reglas que no se repiten en otro lado:
- El rol protegido (Administrador) no se renombra, no se borra y siempre tiene todos los
  permisos; solo su descripción se edita.
- Dos roles no pueden llamarse igual sin importar mayúsculas, ni tener exactamente los mismos
  permisos, salvo ninguno: un rol recién creado puede esperar a que lo configuren.
- Nadie cambia los permisos de su propio rol: evita darse permisos a uno mismo y quitarse por
  error el acceso a la pantalla en la que está.

Cada operación hace un solo `commit()`.
"""

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import delete, func, text
from sqlmodel import Session, col, select

from app.accounts.errors import CannotEditOwnRole, RoleInUse, RoleProtected
from app.accounts.models import Role, RolePermission, UserAccount
from app.accounts.permissions import PERMISSIONS
from app.accounts.schemas import RoleDetail, RoleInput
from app.accounts.services.manager_guard import MANAGE_USERS, ensure_user_managers_remain
from app.accounts.services.role_queries import get_role, registered_permissions_of
from app.common.database import database_conflicts
from app.common.errors import InvalidFields, NotFound

# Llave fija del bloqueo de asesoría que pone en fila las escrituras de roles. Cualquier
# número sirve mientras ningún otro bloqueo de asesoría de la aplicación use el mismo.
ROLE_WRITES_LOCK = 4_004_001

_NAME_TAKEN = "Ya existe un rol con ese nombre."
_NAME_UNIQUE_INDEX = "uq_role_name_lower"
_ROLE_FOREIGN_KEY = "user_account_role_id_fkey"


def lock_role_writes(session: Session) -> None:
    """Pone en fila, hasta el final de la transacción, las escrituras de roles (crear, editar,
    borrar) y los cambios de rol de las personas.

    Sin él, dos altas simultáneas con los mismos permisos pasarían las dos la revisión de
    repetidos (ninguna ve aún la fila de la otra, y la base no puede comparar conjuntos de
    filas), y otra petición podría quitarle `users.manage` a un rol, o borrar el rol que se
    está asignando, mientras se revisa. Con un puñado de roles, ponerlas en fila no cuesta
    nada."""
    session.exec(text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=ROLE_WRITES_LOCK))


def _check_permissions(codes: Iterable[str]) -> frozenset[str]:
    """Los códigos sin repetir, si todos existen y traen lo que necesitan."""
    unique = frozenset(codes)
    problems = [f"Permiso desconocido: {code}." for code in sorted(unique - PERMISSIONS.keys())]
    if not problems:
        # En el orden del registro, que es el de la matriz que ve el administrador.
        problems = [
            f"{info.description} necesita {PERMISSIONS[required].description}."
            for code, info in PERMISSIONS.items()
            if code in unique
            for required in info.requires
            if required not in unique
        ]
    if problems:
        raise InvalidFields(fields={"permissions": problems})
    return unique


def _check_unique_name(session: Session, name: str, exclude_id: int | None = None) -> None:
    statement = select(Role.id).where(func.lower(Role.name) == name.lower())
    if exclude_id is not None:
        statement = statement.where(Role.id != exclude_id)
    if session.exec(statement).first() is not None:
        raise InvalidFields(fields={"name": [_NAME_TAKEN]})


def _check_unique_permissions(
    session: Session, codes: frozenset[str], exclude_id: int | None = None
) -> None:
    if not codes:
        return
    grants: dict[int, set[str]] = defaultdict(set)
    for role_id, code in session.exec(select(RolePermission.role_id, RolePermission.permission)):
        if code in PERMISSIONS and role_id != exclude_id:
            grants[role_id].add(code)
    twin = next((role_id for role_id, granted in grants.items() if granted == codes), None)
    if twin is not None:
        name = session.get(Role, twin).name
        raise InvalidFields(
            fields={"permissions": [f"El rol {name} ya tiene exactamente estos permisos."]}
        )


_CONFLICTS = {
    _NAME_UNIQUE_INDEX: lambda: InvalidFields(fields={"name": [_NAME_TAKEN]}),
    _ROLE_FOREIGN_KEY: RoleInUse,
}


def _database_conflicts(session: Session):
    return database_conflicts(session, _CONFLICTS)


def _read_role(session: Session, role_id: int) -> Role:
    """El rol leído de nuevo de la base, aunque ya esté en la sesión."""
    role = session.get(Role, role_id, populate_existing=True)
    if role is None:
        raise NotFound()
    return role


def create_role(session: Session, data: RoleInput) -> RoleDetail:
    codes = _check_permissions(data.permissions)
    lock_role_writes(session)
    _check_unique_name(session, data.name)
    _check_unique_permissions(session, codes)

    with _database_conflicts(session):
        role = Role(name=data.name, description=data.description)
        session.add(role)
        session.flush()
        session.add_all(RolePermission(role_id=role.id, permission=code) for code in codes)
        session.commit()
    return get_role(session, role.id)


def update_role(session: Session, actor: UserAccount, role_id: int, data: RoleInput) -> RoleDetail:
    codes = _check_permissions(data.permissions)
    # Primero el bloqueo y después la lectura: otra petición pudo cambiar el rol mientras
    # esta esperaba.
    lock_role_writes(session)
    role = _read_role(session, role_id)
    current = registered_permissions_of(session, role.id)
    permissions_changed = codes != current

    if role.is_protected and (data.name != role.name or permissions_changed):
        raise RoleProtected()
    if permissions_changed and actor.role_id == role.id:
        raise CannotEditOwnRole()
    _check_unique_name(session, data.name, exclude_id=role.id)
    if permissions_changed:
        _check_unique_permissions(session, codes, exclude_id=role.id)
    if MANAGE_USERS in current and MANAGE_USERS not in codes:
        members = select(UserAccount.id).where(
            UserAccount.role_id == role.id, UserAccount.is_active
        )
        ensure_user_managers_remain(session, leaving=set(session.exec(members).all()))

    with _database_conflicts(session):
        role.name, role.description = data.name, data.description
        if permissions_changed:
            _replace_permissions(session, role, codes)
        session.commit()
    return get_role(session, role.id)


def _replace_permissions(session: Session, role: Role, codes: frozenset[str]) -> None:
    # También borra las filas de códigos retirados del registro: el rol queda con lo enviado.
    session.exec(
        delete(RolePermission).where(
            RolePermission.role_id == role.id, col(RolePermission.permission).not_in(codes)
        )
    )
    stored = session.exec(
        select(RolePermission.permission).where(RolePermission.role_id == role.id)
    ).all()
    session.add_all(
        RolePermission(role_id=role.id, permission=code) for code in codes - set(stored)
    )
    # Cambiar solo los permisos no toca la fila del rol, y su fecha de edición debe moverse.
    role.updated_at = func.now()


def _has_accounts(session: Session, role_id: int) -> bool:
    """Activas o inactivas: una inactiva conserva su rol para cuando la reactiven."""
    statement = select(UserAccount.id).where(UserAccount.role_id == role_id).limit(1)
    return session.exec(statement).first() is not None


def delete_role(session: Session, role_id: int) -> None:
    # En fila con los cambios de rol: nadie asigna este rol mientras se revisa si está en uso.
    lock_role_writes(session)
    role = _read_role(session, role_id)
    if role.is_protected:
        raise RoleProtected()
    if _has_accounts(session, role.id):
        raise RoleInUse()

    with _database_conflicts(session):
        session.delete(role)
        session.commit()
