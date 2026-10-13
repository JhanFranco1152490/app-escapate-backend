"""Ingreso con Google (OpenID Connect, authorization code + PKCE).

Google solo responde quién es la persona; el acceso lo da que el administrador la haya
registrado antes. Nunca se crean cuentas desde aquí.
"""

import hmac
from functools import cache
from urllib.parse import urlencode

import httpx2
import jwt
from sqlmodel import Session, col, select

from app.accounts.identifiers import normalize_email
from app.accounts.models import LoginMethod, UserAccount
from app.accounts.services.sessions import TokenPair, open_session
from app.core.config import settings

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
_TIMEOUT_SECONDS = 10


class GoogleLoginError(Exception):
    """Fallo del ingreso con Google; `code` es lo que ve el frontend en ?error=."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def authorization_url(state: str, nonce: str, code_challenge: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        # En un equipo compartido evita entrar con la cuenta de Google de otra persona que
        # dejó su sesión abierta en el navegador.
        "prompt": "select_account",
    }
    return f"{AUTHORIZATION_URL}?{urlencode(params)}"


def _http_client() -> httpx2.Client:
    return httpx2.Client(timeout=_TIMEOUT_SECONDS)


@cache
def _jwks_client() -> jwt.PyJWKClient:
    # Las llaves públicas de Google cambian cada tanto; el cliente las guarda en caché.
    return jwt.PyJWKClient(JWKS_URL, cache_keys=True, timeout=_TIMEOUT_SECONDS)


def _signing_key(id_token: str):
    return _jwks_client().get_signing_key_from_jwt(id_token).key


def _exchange_code(code: str, code_verifier: str) -> str:
    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    try:
        with _http_client() as client:
            response = client.post(TOKEN_URL, data=data)
        body = response.json() if response.is_success else {}
    except (httpx2.TransportError, ValueError) as exc:
        raise GoogleLoginError("google_failed") from exc
    id_token = body.get("id_token") if isinstance(body, dict) else None
    if not isinstance(id_token, str) or not id_token:
        raise GoogleLoginError("google_failed")
    return id_token


def _verify_id_token(id_token: str, nonce: str) -> dict:
    try:
        claims = jwt.decode(
            id_token,
            _signing_key(id_token),
            algorithms=["RS256"],
            audience=settings.google_client_id,
            issuer=ISSUERS,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        raise GoogleLoginError("google_failed") from exc
    if not hmac.compare_digest(str(claims["nonce"]), nonce):
        raise GoogleLoginError("google_failed")
    if claims.get("email_verified") is not True or not claims.get("email"):
        raise GoogleLoginError("google_failed")
    return claims


def _find_account(session: Session, sub: str, email: str) -> UserAccount | None:
    user = session.exec(select(UserAccount).where(UserAccount.google_sub == sub)).first()
    if user:
        return user
    # Primer ingreso: se toma la cuenta registrada con ese correo solo si no está vinculada
    # a otra cuenta de Google, que no hereda el acceso por tener el mismo correo.
    statement = select(UserAccount).where(
        UserAccount.email == email, col(UserAccount.google_sub).is_(None)
    )
    return session.exec(statement).first()


def login_with_google(
    session: Session, code: str, code_verifier: str, nonce: str, ip: str
) -> tuple[UserAccount, TokenPair]:
    if not settings.google_client_id:
        raise GoogleLoginError("google_failed")
    claims = _verify_id_token(_exchange_code(code, code_verifier), nonce)
    user = _find_account(session, str(claims["sub"]), normalize_email(claims["email"]))
    if user is None:
        raise GoogleLoginError("account_not_registered")
    if not user.is_active:
        raise GoogleLoginError("account_inactive")
    user.google_sub = str(claims["sub"])
    pair = open_session(session, user, LoginMethod.GOOGLE, ip)
    session.commit()
    return user, pair
