import hmac
import secrets

from fastapi import Request

from app.common.errors import PermissionDenied
from app.core.security.cookies import CSRF_COOKIE

CSRF_HEADER = "X-CSRF-Token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_protect(request: Request) -> None:
    """Exige que la cabecera X-CSRF-Token coincida con la cookie en toda mutación de la API.

    El frontend vive en otro subdominio y no puede leer la cookie de la API: recibe el token
    en el cuerpo de GET /api/auth/csrf y lo reenvía en la cabecera.
    """
    if request.method in _SAFE_METHODS or not request.url.path.startswith("/api/"):
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise PermissionDenied(
            "La solicitud no es válida. Recarga la página e inténtalo de nuevo."
        )
