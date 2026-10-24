"""Regla que impide dejar a la agencia sin nadie que pueda gestionar usuarios.

Siempre queda al menos una persona activa cuyo rol tenga `users.manage`. Con ella basta para
recuperar todo lo demás: quien gestiona usuarios puede crear o reasignar a un Administrador.
"""

from collections.abc import Collection

from sqlmodel import Session, select

from app.accounts.errors import LastUserManager
from app.accounts.models import RolePermission, UserAccount

MANAGE_USERS = "users.manage"


def ensure_user_managers_remain(session: Session, leaving: Collection[int]) -> None:
    """Falla si, sin las cuentas de `leaving`, no queda ninguna activa con `users.manage`.

    Bloquea las filas de los gestores activos hasta el final de la transacción, siempre en
    orden de id: dos cambios simultáneos se esperan uno al otro en vez de bloquearse entre
    sí, y el segundo ve, al despertar, quién sigue activo. Por eso se llama antes de bloquear
    cualquier otra cuenta.
    """
    managers = session.exec(
        select(UserAccount.id)
        .join(RolePermission, RolePermission.role_id == UserAccount.role_id)
        .where(RolePermission.permission == MANAGE_USERS, UserAccount.is_active)
        .order_by(UserAccount.id)
        .with_for_update(of=UserAccount)
    ).all()
    if managers and set(managers) <= set(leaving):
        raise LastUserManager()
