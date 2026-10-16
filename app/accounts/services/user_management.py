"""Gestión de usuarios por el administrador: alta, edición, desactivar y activar, reenviar la
invitación y desvincular Google.

Cada operación hace un solo `commit()`. Los correos se envían después de ese commit: una
llamada externa nunca ocurre dentro de la transacción.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.accounts.errors import (
    CannotDeactivateSelf,
    DuplicateUser,
    EmailDeliveryFailed,
    InvalidFields,
    InvitationNotPending,
    LastUserManager,
    UserInactive,
)
from app.accounts.models import RevokeReason, Role, RolePermission, UserAccount
from app.accounts.schemas import UserCreate, UserInput
from app.accounts.services.password_reset import send_invitation
from app.accounts.services.sessions import revoke_all
from app.common.email import EmailDeliveryError
from app.common.errors import NotFound

logger = logging.getLogger(__name__)

MANAGE_USERS = "users.manage"

# Restricción única de la base -> campo del formulario. La base responde esto cuando dos altas
# simultáneas pasan la revisión previa.
_UNIQUE_FIELDS = {
    "user_account_email_key": "email",
    "uq_user_account_document": "document_number",
    "uq_user_account_phone": "phone",
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
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint in _UNIQUE_FIELDS:
            # Sin encadenar el error original: su mensaje trae el valor repetido.
            raise DuplicateUser([_UNIQUE_FIELDS[constraint]]) from None
        raise


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
    # Siempre en el mismo orden, para que dos desactivaciones simultáneas se esperen una a
    # la otra en vez de bloquearse entre sí. La segunda ve, al despertar, quién sigue activo.
    managers = session.exec(
        select(UserAccount.id)
        .join(RolePermission, RolePermission.role_id == UserAccount.role_id)
        .where(RolePermission.permission == MANAGE_USERS, UserAccount.is_active)
        .order_by(UserAccount.id)
        .with_for_update(of=UserAccount)
    ).all()
    user = _lock(session, user_id)
    if not user.is_active:
        return user
    if user.id in managers and len(managers) == 1:
        raise LastUserManager()

    user.is_active = False
    revoke_all(session, user.id, RevokeReason.ACCOUNT_DISABLED)
    _commit(session)
    return user


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
