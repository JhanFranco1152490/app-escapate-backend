"""Recuperación de contraseña e invitación: los dos terminan creando una contraseña desde un
enlace que llega al correo de la cuenta."""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Session, select

from app.accounts.errors import InvalidPassword
from app.accounts.models import LoginMethod, RevokeReason, UserAccount
from app.accounts.passwords import password_problems
from app.accounts.services import lockout
from app.accounts.services.password_login import find_by_document
from app.accounts.services.reset_tokens import LIFETIMES, TokenPurpose, make_token, read_token
from app.accounts.services.sessions import TokenPair, open_session, revoke_all
from app.common.dates import BOGOTA
from app.common.email import EmailDeliveryError, send_email
from app.common.identifiers import normalize_document
from app.core.config import settings
from app.core.security.passwords import hash_password

logger = logging.getLogger(__name__)

_LINKS = {
    TokenPurpose.RESET: (
        "/restablecer-contrasena",
        "password_reset",
        "Recupera tu contraseña de Escápate",
    ),
    TokenPurpose.INVITATION: ("/crear-contrasena", "invitation", "Te dieron acceso a Escápate"),
}


@dataclass(frozen=True)
class PendingEmail:
    """Un correo listo para enviar sin la sesión de base de datos de la petición: así se puede
    mandar en segundo plano, cuando la petición ya terminó."""

    user_id: int
    to: str
    subject: str
    template: str
    context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ConfirmResult:
    user: UserAccount
    pair: TokenPair
    notice: PendingEmail | None


def _expires_in(purpose: TokenPurpose) -> str:
    minutes = int(LIFETIMES[purpose].total_seconds()) // 60
    return f"{minutes // 60} horas" if minutes % 60 == 0 else f"{minutes} minutos"


def _link_email(user: UserAccount, purpose: TokenPurpose) -> PendingEmail:
    path, template, subject = _LINKS[purpose]
    # El token va después de "#": el navegador no lo envía a ningún servidor ni en el Referer.
    link = f"{settings.frontend_origin}{path}#token={make_token(user, purpose)}"
    context = {"name": user.full_name, "link": link, "expires_in": _expires_in(purpose)}
    return PendingEmail(user.id, user.email, subject, template, context)


def _change_notice(user: UserAccount) -> PendingEmail:
    now = datetime.now(BOGOTA)
    context = {
        "name": user.full_name,
        "date": now.strftime("%d/%m/%Y"),
        "time": now.strftime("%H:%M"),
    }
    return PendingEmail(
        user.id, user.email, "Tu contraseña de Escápate cambió", "password_changed", context
    )


def _send(email: PendingEmail) -> None:
    send_email(
        to=email.to,
        subject=email.subject,
        domain="accounts",
        name=email.template,
        context=email.context,
    )


def request_reset(session: Session, document_type: str, raw_number: str) -> PendingEmail | None:
    """El correo de recuperación si el documento es de una cuenta activa; si no, nada.

    Quien llama responde lo mismo en los dos casos, para no revelar qué documentos existen.
    """
    user = find_by_document(session, document_type, normalize_document(raw_number))
    if user is None or not user.is_active:
        return None
    return _link_email(user, TokenPurpose.RESET)


def deliver(email: PendingEmail) -> None:
    """Envía en segundo plano: la respuesta ya salió, así que un fallo solo se registra."""
    try:
        _send(email)
    except EmailDeliveryError as error:
        # Solo la clase y el id: el mensaje de un error de correo puede traer la dirección.
        logger.warning(
            "No se envió el correo %s a la cuenta %s: %s",
            email.template,
            email.user_id,
            type(error).__name__,
        )


def send_invitation(user: UserAccount) -> None:
    """Envía la invitación ahora; deja pasar `EmailDeliveryError` para que se pueda reintentar."""
    _send(_link_email(user, TokenPurpose.INVITATION))


def check(session: Session, token: str) -> tuple[UserAccount, TokenPurpose]:
    return read_token(session, token)


def _password_fields(user: UserAccount, password: str, confirmation: str) -> dict[str, list[str]]:
    fields = {}
    problems = password_problems(password, email=user.email, document_number=user.document_number)
    if problems:
        fields["password"] = problems
    if password != confirmation:
        fields["password_confirmation"] = ["Las contraseñas no coinciden."]
    return fields


def confirm(
    session: Session, token: str, password: str, confirmation: str, ip: str
) -> ConfirmResult:
    user, _ = read_token(session, token)
    # Con la fila bloqueada se vuelve a leer el token: dos envíos simultáneos del mismo enlace
    # no pueden usarlo los dos.
    session.exec(
        select(UserAccount)
        .where(UserAccount.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    user, purpose = read_token(session, token)

    fields = _password_fields(user, password, confirmation)
    if fields:
        raise InvalidPassword(fields=fields)

    user.password_hash = hash_password(password)
    revoke_all(session, user.id, RevokeReason.PASSWORD_CHANGED)
    # Demostró controlar el correo de la cuenta: sus bloqueos por intentos no tienen por qué
    # seguir, en ninguna IP.
    lockout.clear_document_locks(
        session, lockout.lock_identifier(user.document_type, user.document_number)
    )
    pair = open_session(session, user, LoginMethod.EMAIL_LINK, ip)
    session.commit()
    notice = _change_notice(user) if purpose == TokenPurpose.RESET else None
    return ConfirmResult(user, pair, notice)
