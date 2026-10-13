"""Sesiones: emitir, rotar y revocar refresh tokens. Común a todas las formas de entrar."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.accounts.models import LoginEvent, LoginMethod, RefreshToken, RevokeReason, UserAccount
from app.common.errors import AuthenticationFailed
from app.core.security.tokens import REFRESH_TTL, create_token, decode_token

MAX_SESSIONS = 3
# Dos pestañas que renuevan a la vez envían el mismo token: la segunda llega cuando la
# primera ya lo rotó. Dentro de esta ventana eso no se toma como robo.
ROTATION_GRACE = timedelta(seconds=30)
LOGIN_EVENT_RETENTION = timedelta(days=90)


@dataclass(frozen=True)
class TokenPair:
    access: str
    refresh: str


def _now() -> datetime:
    return datetime.now(UTC)


def _issue(session: Session, user: UserAccount, now: datetime) -> TokenPair:
    jti = secrets.token_urlsafe(32)
    session.add(
        RefreshToken(jti=jti, user_id=user.id, issued_at=now, expires_at=now + REFRESH_TTL)
    )
    subject = str(user.id)
    return TokenPair(
        create_token(subject, "access", session_id=jti), create_token(subject, "refresh", jti=jti)
    )


def _active_tokens(session: Session, user_id: int, now: datetime) -> list[RefreshToken]:
    statement = (
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            col(RefreshToken.revoked_at).is_(None),
            RefreshToken.expires_at > now,
        )
        .order_by(RefreshToken.issued_at, RefreshToken.id)
    )
    return list(session.exec(statement).all())


def _revoke_tokens(tokens: list[RefreshToken], reason: RevokeReason, now: datetime) -> None:
    for token in tokens:
        token.revoked_at, token.revoke_reason = now, reason


def open_session(session: Session, user: UserAccount, method: LoginMethod, ip: str) -> TokenPair:
    """Abre una sesión tras un ingreso exitoso. No hace commit: lo hace quien la llama."""
    now = _now()
    # Bloquear la fila de la cuenta serializa dos ingresos simultáneos: los dos no pueden
    # contar las mismas sesiones abiertas y saltarse el límite.
    session.exec(select(UserAccount).where(UserAccount.id == user.id).with_for_update()).one()
    session.exec(
        delete(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.expires_at <= now)
    )
    active = _active_tokens(session, user.id, now)
    _revoke_tokens(
        active[: max(0, len(active) - MAX_SESSIONS + 1)], RevokeReason.SESSION_LIMIT, now
    )
    pair = _issue(session, user, now)
    session.add(LoginEvent(user_id=user.id, method=method, ip=ip))
    user.last_activity_at = now
    session.exec(delete(LoginEvent).where(LoginEvent.created_at < now - LOGIN_EVENT_RETENTION))
    return pair


def _find_token(session: Session, refresh: str) -> RefreshToken:
    payload = decode_token(refresh, "refresh")
    jti = payload.get("jti")
    if not jti:
        raise AuthenticationFailed()
    statement = select(RefreshToken).where(RefreshToken.jti == jti).with_for_update()
    token = session.exec(statement).first()
    if token is None or str(token.user_id) != payload["sub"]:
        raise AuthenticationFailed()
    return token


def rotate(session: Session, refresh: str) -> TokenPair:
    now = _now()
    token = _find_token(session, refresh)
    if token.revoked_at is not None:
        stolen = (
            token.revoke_reason == RevokeReason.ROTATED and now - token.revoked_at > ROTATION_GRACE
        )
        if stolen:
            # Un token ya rotado que vuelve a usarse lo tiene alguien más: se cierran todas
            # las sesiones de la cuenta. Se guarda antes de responder el error.
            revoke_all(session, token.user_id, RevokeReason.REUSE_DETECTED)
            session.commit()
        raise AuthenticationFailed()
    user = session.get(UserAccount, token.user_id)
    if token.expires_at <= now or user is None or not user.is_active:
        raise AuthenticationFailed()
    _revoke_tokens([token], RevokeReason.ROTATED, now)
    pair = _issue(session, user, now)
    user.last_activity_at = now
    session.commit()
    return pair


def is_session_open(session: Session, session_id: str) -> bool:
    """Si el refresh token al que está atado un access token sigue vigente.

    Uno ya rotado cuenta como abierto: la renovación lo reemplazó pero su access token vive
    hasta vencer (dos pestañas pueden seguir usándolo unos segundos). Cerrado por logout,
    límite de sesiones, robo o cuenta desactivada, el access token deja de servir al instante.
    """
    token = session.exec(select(RefreshToken).where(RefreshToken.jti == session_id)).first()
    if token is None:
        return False
    return token.revoked_at is None or token.revoke_reason == RevokeReason.ROTATED


def revoke(session: Session, refresh: str, reason: RevokeReason) -> None:
    """Cierra la sesión de ese token. Un token inválido o ya cerrado no hace nada."""
    try:
        token = _find_token(session, refresh)
    except AuthenticationFailed:
        return
    if token.revoked_at is None:
        _revoke_tokens([token], reason, _now())
        session.commit()


def revoke_all(session: Session, user_id: int, reason: RevokeReason) -> None:
    """Cierra todas las sesiones de la cuenta. No hace commit."""
    now = _now()
    _revoke_tokens(_active_tokens(session, user_id, now), reason, now)
