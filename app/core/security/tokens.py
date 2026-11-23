from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt

from app.common.errors import AuthenticationFailed
from app.core.config import settings

TokenType = Literal["access", "refresh"]
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=7)
_ALGORITHM = "HS256"
_TTL = {"access": ACCESS_TTL, "refresh": REFRESH_TTL}
# La fecha de emisión se guarda en segundos enteros: con relojes que difieren unos milisegundos
# (réplicas distintas, o un salto del reloj) un token recién emitido parecería venir del futuro
# y se rechazaría una petición cualquiera. Esta tolerancia también aplica a la expiración.
_CLOCK_LEEWAY_SECONDS = 10


def create_token(
    subject: str,
    token_type: TokenType,
    jti: str | None = None,
    session_id: str | None = None,
) -> str:
    now = datetime.now(UTC)
    payload = {"sub": subject, "type": token_type, "iat": now, "exp": now + _TTL[token_type]}
    if jti:
        payload["jti"] = jti
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str, token_type: TokenType) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[_ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
            leeway=_CLOCK_LEEWAY_SECONDS,
        )
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailed() from exc
    if payload["type"] != token_type:
        raise AuthenticationFailed()
    return payload
