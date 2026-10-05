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


def create_token(subject: str, token_type: TokenType, jti: str | None = None) -> str:
    now = datetime.now(UTC)
    payload = {"sub": subject, "type": token_type, "iat": now, "exp": now + _TTL[token_type]}
    if jti:
        payload["jti"] = jti
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str, token_type: TokenType) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[_ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailed() from exc
    if payload["type"] != token_type:
        raise AuthenticationFailed()
    return payload
