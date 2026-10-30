"""Ingreso con tipo y número de documento + contraseña, con bloqueo por intentos fallidos."""

import secrets
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.accounts.errors import AccountInactive, AccountLocked, InvalidCredentials
from app.accounts.models import LoginMethod, UserAccount
from app.accounts.services import lockout
from app.accounts.services.sessions import TokenPair, open_session
from app.common.identifiers import is_valid_document, normalize_document
from app.core.security.passwords import hash_password, verify_password

# Sin cuenta (o sin contraseña) se verifica contra este hash, para que la respuesta tarde lo
# mismo que con una cuenta real y el tiempo no revele qué documentos están registrados.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def find_by_document(session: Session, document_type: str, number: str) -> UserAccount | None:
    """La cuenta de ese documento ya normalizado, o None si el formato no es válido."""
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
    identifier = lockout.lock_identifier(document_type, number)
    if lockout.is_locked(session, identifier, ip, now):
        raise AccountLocked()

    user = find_by_document(session, document_type, number)
    stored_hash = user.password_hash if user and user.password_hash else None
    valid, new_hash = verify_password(password, stored_hash or _DUMMY_HASH)
    if not (valid and stored_hash):
        lockout.register_failure(session, identifier, ip, now)
        session.commit()
        raise InvalidCredentials()
    # Solo se dice que la cuenta está inactiva a quien ya demostró conocer la contraseña.
    if not user.is_active:
        raise AccountInactive()

    lockout.clear_ip(session, identifier, ip)
    if new_hash:
        user.password_hash = new_hash
    pair = open_session(session, user, LoginMethod.DOCUMENT, ip)
    session.commit()
    return user, pair
