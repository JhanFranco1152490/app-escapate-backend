"""Bloqueo por intentos fallidos del ingreso con documento.

Cada documento tiene una fila por IP (tope `MAX_FAILURES`) y una fila con `ip = ANY_IP` que
suma los fallos de todas las IP (tope `MAX_FAILURES_ANY_IP`).
"""

import hashlib
import hmac
from datetime import datetime, timedelta

from sqlalchemy import and_, case, delete, or_
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, col, select

from app.accounts.models import LoginAttempt
from app.core.config import settings

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


def lock_identifier(document_type: str, number: str) -> str:
    """HMAC del documento: identifica la pareja del bloqueo sin guardar el documento."""
    message = f"{document_type}:{number}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def is_locked(session: Session, identifier: str, ip: str, now: datetime) -> bool:
    statement = select(LoginAttempt.locked_until).where(
        LoginAttempt.identifier == identifier, col(LoginAttempt.ip).in_([ip, ANY_IP])
    )
    return any(locked_until and locked_until > now for locked_until in session.exec(statement))


def _count_failure(session: Session, identifier: str, ip: str, now: datetime, limit: int) -> None:
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


def register_failure(session: Session, identifier: str, ip: str, now: datetime) -> None:
    _count_failure(session, identifier, ip, now, MAX_FAILURES)
    _count_failure(session, identifier, ANY_IP, now, MAX_FAILURES_ANY_IP)


def clear_ip(session: Session, identifier: str, ip: str) -> None:
    """Tras un ingreso exitoso: solo la fila de esa IP.

    La del documento se conserva: si un ingreso la borrara, quien ataca desde varias IP la
    reiniciaría con un ingreso válido propio.
    """
    session.exec(
        delete(LoginAttempt).where(
            col(LoginAttempt.identifier) == identifier, col(LoginAttempt.ip) == ip
        )
    )


def clear_document_locks(session: Session, identifier: str) -> None:
    """Todas las filas del documento, en cualquier IP.

    Solo para quien demostró controlar el correo de la cuenta (recuperación de contraseña):
    no puede usarse para reiniciar el conteo de un documento ajeno.
    """
    session.exec(delete(LoginAttempt).where(col(LoginAttempt.identifier) == identifier))
