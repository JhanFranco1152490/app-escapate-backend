"""Ingreso con tipo y número de documento + contraseña, con bloqueo por intentos fallidos."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, delete, or_
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, col, select

from app.accounts.errors import AccountInactive, AccountLocked, InvalidCredentials
from app.accounts.identifiers import is_valid_document, normalize_document
from app.accounts.models import LoginAttempt, LoginMethod, UserAccount
from app.accounts.services.sessions import TokenPair, open_session
from app.core.config import settings
from app.core.security.passwords import hash_password, verify_password

MAX_FAILURES = 5
# Tope para un mismo documento sumando todas las IP: quien rota de IP no llega a 5 en
# ninguna, pero sí a este. Es más alto para que no sirva de forma barata para dejar fuera a
# una persona escribiendo su documento a propósito.
MAX_FAILURES_ANY_IP = 20
LOCK_DURATION = timedelta(minutes=15)
# Los fallos más viejos que esto dejan de sumar: sin una ventana, unos pocos errores de
# digitación repartidos en meses acabarían bloqueando la cuenta.
FAILURE_WINDOW = timedelta(minutes=15)
# Valor de `ip` de la fila que cuenta los fallos del documento en todas las IP.
ANY_IP = "*"
# Sin cuenta (o sin contraseña) se verifica contra este hash, para que la respuesta tarde lo
# mismo que con una cuenta real y el tiempo no revele qué documentos están registrados.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def lock_identifier(document_type: str, number: str) -> str:
    """HMAC del documento: identifica la pareja del bloqueo sin guardar el documento."""
    message = f"{document_type}:{number}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def _is_locked(session: Session, identifier: str, ip: str, now: datetime) -> bool:
    statement = select(LoginAttempt.locked_until).where(
        LoginAttempt.identifier == identifier, col(LoginAttempt.ip).in_([ip, ANY_IP])
    )
    return any(locked_until and locked_until > now for locked_until in session.exec(statement))


def _register_failure(
    session: Session, identifier: str, ip: str, now: datetime, limit: int
) -> None:
    # Un solo INSERT ... ON CONFLICT: dos intentos simultáneos no pueden contar uno solo.
    table = LoginAttempt.__table__
    lock_expired = and_(table.c.locked_until.isnot(None), table.c.locked_until <= now)
    restarts = or_(lock_expired, table.c.updated_at <= now - FAILURE_WINDOW)
    failures = case((restarts, 1), else_=table.c.failures + 1)
    statement = insert(table).values(identifier=identifier, ip=ip, failures=1, updated_at=now)
    statement = statement.on_conflict_do_update(
        index_elements=["identifier", "ip"],
        set_={
            "failures": failures,
            "locked_until": case((failures >= limit, now + LOCK_DURATION), else_=None),
            "updated_at": now,
        },
    )
    session.exec(statement)


def _clear_failures(session: Session, identifier: str, ip: str) -> None:
    session.exec(
        delete(LoginAttempt).where(
            col(LoginAttempt.identifier) == identifier, col(LoginAttempt.ip) == ip
        )
    )


def _find_account(session: Session, document_type: str, number: str) -> UserAccount | None:
    if not is_valid_document(document_type, number):
        return None
    statement = select(UserAccount).where(
        UserAccount.document_type == document_type, UserAccount.document_number == number
    )
    return session.exec(statement).first()


def login_with_document(
    session: Session, document_type: str, raw_number: str, password: str, ip: str
) -> tuple[UserAccount, TokenPair]:
    now = datetime.now(UTC)
    number = normalize_document(raw_number)
    identifier = lock_identifier(document_type, number)
    if _is_locked(session, identifier, ip, now):
        raise AccountLocked()

    user = _find_account(session, document_type, number)
    stored_hash = user.password_hash if user and user.password_hash else None
    valid, new_hash = verify_password(password, stored_hash or _DUMMY_HASH)
    if not (valid and stored_hash):
        _register_failure(session, identifier, ip, now, MAX_FAILURES)
        _register_failure(session, identifier, ANY_IP, now, MAX_FAILURES_ANY_IP)
        session.commit()
        raise InvalidCredentials()
    # Solo se dice que la cuenta está inactiva a quien ya demostró conocer la contraseña.
    if not user.is_active:
        raise AccountInactive()

    _clear_failures(session, identifier, ip)
    if new_hash:
        user.password_hash = new_hash
    pair = open_session(session, user, LoginMethod.DOCUMENT, ip)
    session.commit()
    return user, pair
