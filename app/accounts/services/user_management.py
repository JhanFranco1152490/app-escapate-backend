"""Gestión de usuarios por el administrador: alta, edición, cambio de rol, desactivar y
activar, reenviar la invitación y desvincular Google.

Cada operación hace un solo `commit()`. Los correos se envían después de ese commit: una
llamada externa nunca ocurre dentro de la transacción.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.accounts.errors import (
    CannotChangeOwnRole,
    CannotDeactivateSelf,
    DuplicateUser,
    EmailDeliveryFailed,
    InvitationNotPending,
    UserInactive,
)
from app.accounts.models import RevokeReason, Role, UserAccount
from app.accounts.schemas import UserCreate, UserInput
from app.accounts.services.manager_guard import MANAGE_USERS, ensure_user_managers_remain
from app.accounts.services.password_reset import PendingEmail, deliver, send_invitation
from app.accounts.services.role_management import lock_role_writes
from app.accounts.services.role_queries import registered_permissions_of
from app.accounts.services.sessions import revoke_all
from app.common.database import database_conflicts
from app.common.email import EmailDeliveryError
from app.common.errors import InvalidFields, NotFound

logger = logging.getLogger(__name__)

# Restricción única de la base -> campo del formulario. La base responde esto cuando dos altas
# simultáneas pasan la revisión previa.
_UNIQUE_FIELDS = {
    "user_account_email_key": "email",
    "uq_user_account_document": "document_number",
    "uq_user_account_phone": "phone",
}
_UNIQUE_ERRORS = {
    constraint: (lambda field=field: DuplicateUser([field]))
    for constraint, field in _UNIQUE_FIELDS.items()
}


@dataclass(frozen=True)
class SaveResult:
    user: UserAccount
    # None si no hizo falta enviar la invitación; False si se intentó y falló.
    invitation_sent: bool | None


def _duplicate_fields(
    session: Session, data: UserInput, exclude_id: int | None = None
) -> list[str]:
    """Los campos de `data` que ya tiene otra cuenta."""
    same_data = or_(
        UserAccount.email == data.email,
        and_(
            UserAccount.document_type == data.document_type,
            UserAccount.document_number == data.document_number,
        ),
        UserAccount.phone == data.phone,
    )
    statement = select(UserAccount).where(same_data)
    if exclude_id is not None:
        statement = statement.where(UserAccount.id != exclude_id)
    others = session.exec(statement).all()
    taken = []
    if any(other.email == data.email for other in others):
        taken.append("email")
    if any(
        (other.document_type, other.document_number) == (data.document_type, data.document_number)
        for other in others
    ):
        taken.append("document_number")
    if any(other.phone == data.phone for other in others):
        taken.append("phone")
    return taken


def _commit(session: Session) -> None:
    with database_conflicts(session, _UNIQUE_ERRORS):
        session.commit()


def _lock(session: Session, user_id: int) -> UserAccount:
    """La cuenta con su fila bloqueada y leída de nuevo: otra petición pudo cambiarla."""
    statement = (
        select(UserAccount)
        .where(UserAccount.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    user = session.exec(statement).first()
    if user is None:
        raise NotFound()
    return user


def _invite(user: UserAccount) -> bool:
    try:
        send_invitation(user)
    except EmailDeliveryError as error:
        # Solo la clase y el id: el mensaje de un error de correo puede traer la dirección.
        logger.warning(
            "No se envió la invitación a la cuenta %s: %s", user.id, type(error).__name__
        )
        return False
    return True


def create_user(session: Session, data: UserCreate) -> SaveResult:
    if session.get(Role, data.role_id) is None:
        raise InvalidFields(fields={"role_id": ["El rol no existe."]})
    taken = _duplicate_fields(session, data)
    if taken:
        raise DuplicateUser(taken)

    user = UserAccount(**data.model_dump(mode="json"))
    session.add(user)
    _commit(session)
    return SaveResult(user, _invite(user))


def update_user(session: Session, user_id: int, data: UserInput) -> SaveResult:
    user = _lock(session, user_id)
    taken = _duplicate_fields(session, data, exclude_id=user.id)
    if taken:
        raise DuplicateUser(taken)

    email_changed = user.email != data.email
    for name, value in data.model_dump(mode="json").items():
        setattr(user, name, value)
    if email_changed and user.google_linked:
        # La cuenta de Google vinculada era la del correo anterior.
        user.google_sub = None
        revoke_all(session, user.id, RevokeReason.GOOGLE_UNLINKED)
    # Una cuenta inactiva no recibe la invitación: su enlace no serviría.
    resend = email_changed and not user.has_password and user.is_active
    _commit(session)
    return SaveResult(user, _invite(user) if resend else None)


def deactivate_user(session: Session, actor: UserAccount, user_id: int) -> UserAccount:
    if actor.id == user_id:
        raise CannotDeactivateSelf()
    # Antes de bloquear la cuenta: la regla bloquea primero las filas de los gestores. Si la
    # cuenta ya está inactiva no es gestora activa, así que la regla no la cuenta.
    ensure_user_managers_remain(session, leaving={user_id})
    user = _lock(session, user_id)
    if not user.is_active:
        return user

    user.is_active = False
    revoke_all(session, user.id, RevokeReason.ACCOUNT_DISABLED)
    _commit(session)
    return user


def change_role(session: Session, actor: UserAccount, user_id: int, role_id: int) -> UserAccount:
    user = session.get(UserAccount, user_id)
    if user is None:
        raise NotFound()
    if actor.id == user_id:
        raise CannotChangeOwnRole()

    # Mientras dura el cambio nadie borra el rol nuevo ni cambia los permisos de los roles, que
    # deciden la regla del último gestor. Por eso el rol se lee después del bloqueo.
    lock_role_writes(session)
    new_role = session.get(Role, role_id, populate_existing=True)
    if new_role is None:
        raise InvalidFields(fields={"role_id": ["El rol no existe."]})
    session.refresh(user)
    if user.role_id == role_id:
        return user
    loses_manage_users = MANAGE_USERS in registered_permissions_of(
        session, user.role_id
    ) and MANAGE_USERS not in registered_permissions_of(session, role_id)
    # Antes de bloquear la cuenta, como al desactivar: la regla bloquea primero a los gestores.
    if user.is_active and loses_manage_users:
        ensure_user_managers_remain(session, leaving={user_id})
    user = _lock(session, user_id)
    old_role = session.get(Role, user.role_id)

    user.role_id = role_id
    # Sin cerrar sus sesiones: los permisos se leen en cada petición, así que el rol nuevo
    # aplica desde su siguiente acción.
    _commit(session)
    if user.is_active and (old_role.is_protected or new_role.is_protected):
        deliver(_role_notice(user, old_role.name, new_role.name))
    return user


def _role_notice(user: UserAccount, old_role: str, new_role: str) -> PendingEmail:
    """Solo al dar o quitar el rol Administrador: un ascenso que nadie autorizó es lo que la
    persona querría notar, y avisar de cada cambio entre roles de operación sería ruido."""
    context = {"name": user.full_name, "old_role": old_role, "new_role": new_role}
    return PendingEmail(user.id, user.email, "Tu rol en Escápate cambió", "role_changed", context)


def activate_user(session: Session, user_id: int) -> UserAccount:
    user = _lock(session, user_id)
    user.is_active = True
    _commit(session)
    return user


def resend_invitation(session: Session, user_id: int) -> None:
    user = session.get(UserAccount, user_id)
    if user is None:
        raise NotFound()
    if user.has_password:
        raise InvitationNotPending()
    if not user.is_active:
        raise UserInactive()
    if not _invite(user):
        raise EmailDeliveryFailed()


def unlink_google(session: Session, user_id: int) -> UserAccount:
    user = _lock(session, user_id)
    if user.google_linked:
        user.google_sub = None
        # No se sabe cuáles sesiones se abrieron con Google: se cierran todas.
        revoke_all(session, user.id, RevokeReason.GOOGLE_UNLINKED)
        _commit(session)
    return user
