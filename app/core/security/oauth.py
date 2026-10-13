"""Piezas del flujo OAuth: PKCE y el estado que viaja firmado en una cookie."""

import base64
import hashlib
import secrets

from itsdangerous import BadData, URLSafeTimedSerializer

from app.core.config import settings

STATE_MAX_AGE_SECONDS = 600
_SALT = "google-oauth"


def new_pkce() -> tuple[str, str]:
    """Devuelve (code_verifier, code_challenge S256)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def dump_state(data: dict) -> str:
    return _serializer().dumps(data)


def load_state(value: str | None) -> dict | None:
    """El estado guardado al iniciar; None si falta, venció o fue alterado."""
    if not value:
        return None
    try:
        return _serializer().loads(value, max_age=STATE_MAX_AGE_SECONDS)
    except BadData:
        return None
