"""Enlaces firmados para crear una contraseña: recuperación e invitación.

No se guardan en la base de datos. El token firma el id de la cuenta y una huella de su
correo y su hash de contraseña: al crear la contraseña o corregir el correo, la huella
cambia y todos los enlaces anteriores dejan de valer.
"""

import hashlib
import hmac
from datetime import timedelta
from enum import StrEnum

from itsdangerous import BadData, URLSafeTimedSerializer
from sqlmodel import Session

from app.accounts.errors import InvalidResetToken
from app.accounts.models import UserAccount
from app.core.config import settings


class TokenPurpose(StrEnum):
    RESET = "reset"
    INVITATION = "invitation"


# Un salt por propósito: un enlace de invitación (72 h) no sirve como recuperación.
_SALTS = {TokenPurpose.RESET: "password-reset", TokenPurpose.INVITATION: "invitation"}
LIFETIMES = {
    TokenPurpose.RESET: timedelta(minutes=30),
    TokenPurpose.INVITATION: timedelta(hours=72),
}


def _serializer(purpose: TokenPurpose) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALTS[purpose])


def _fingerprint(user: UserAccount) -> str:
    # El contenido de un token de itsdangerous se puede leer: lleva esta huella, no el
    # correo ni el hash.
    message = f"{user.email}\0{user.password_hash or ''}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()[:16]


def make_token(user: UserAccount, purpose: TokenPurpose) -> str:
    return _serializer(purpose).dumps({"u": user.id, "f": _fingerprint(user)})


def read_token(session: Session, token: str) -> tuple[UserAccount, TokenPurpose]:
    """La cuenta y el propósito del enlace; `InvalidResetToken` si no sirve por algún motivo."""
    for purpose in TokenPurpose:
        max_age = int(LIFETIMES[purpose].total_seconds())
        try:
            data = _serializer(purpose).loads(token, max_age=max_age)
        except BadData:
            continue
        user_id = data.get("u") if isinstance(data, dict) else None
        user = session.get(UserAccount, user_id) if isinstance(user_id, int) else None
        if user is None or not user.is_active:
            break
        if not hmac.compare_digest(str(data.get("f", "")), _fingerprint(user)):
            break
        return user, purpose
    raise InvalidResetToken()
