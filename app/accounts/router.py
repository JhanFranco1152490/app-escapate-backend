import hmac
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.accounts.dependencies import CurrentUser, SessionDep
from app.accounts.models import RevokeReason, UserAccount
from app.accounts.schemas import LoginRequest, RoleSummary, SessionUser
from app.accounts.services import google_login, password_login, sessions
from app.accounts.services.access import permissions_of_role
from app.accounts.services.google_login import GoogleLoginError
from app.common.errors import ErrorResponse, NotAuthenticated
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import oauth
from app.core.security.cookies import (
    OAUTH_COOKIE,
    REFRESH_COOKIE,
    clear_oauth_cookie,
    clear_session_cookies,
    set_csrf_cookie,
    set_oauth_cookie,
    set_session_cookies,
)
from app.core.security.csrf import new_csrf_token
from app.core.security.network import client_ip
from app.core.security.redirects import safe_next_path

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _errors(*statuses: int) -> dict:
    return {status_code: {"model": ErrorResponse} for status_code in statuses}


class CsrfToken(BaseModel):
    csrf_token: str


def _session_user(session: Session, user: UserAccount) -> SessionUser:
    return SessionUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=RoleSummary(id=user.role.id, name=user.role.name),
        permissions=permissions_of_role(session, user.role_id),
    )


@router.get("/csrf")
def get_csrf_token(response: Response) -> CsrfToken:
    token = new_csrf_token()
    set_csrf_cookie(response, token)
    return CsrfToken(csrf_token=token)


@router.post("/login", responses=_errors(401, 403, 429))
@limiter.limit(lambda: settings.rate_login)
def login(
    request: Request, response: Response, data: LoginRequest, session: SessionDep
) -> SessionUser:
    user, pair = password_login.login_with_document(
        session, data.document_type, data.document_number, data.password, client_ip(request)
    )
    set_session_cookies(response, pair.access, pair.refresh)
    return _session_user(session, user)


@router.get("/google/start", response_class=RedirectResponse, status_code=302)
@limiter.limit(lambda: settings.rate_google)
def google_start(request: Request, next_path: str = Query("/", alias="next")) -> Response:
    # Sin cliente configurado Google mostraría su propia página de error; se vuelve al login
    # con el mismo aviso que da el callback.
    if not settings.google_client_id:
        return _back_to_login("google_failed")
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier, challenge = oauth.new_pkce()
    response = RedirectResponse(
        google_login.authorization_url(state, nonce, challenge), status_code=302
    )
    data = {
        "state": state,
        "nonce": nonce,
        "verifier": verifier,
        "next": safe_next_path(next_path),
    }
    set_oauth_cookie(response, oauth.dump_state(data), oauth.STATE_MAX_AGE_SECONDS)
    return response


def _back_to_login(code: str) -> Response:
    response = RedirectResponse(
        f"{settings.frontend_origin}/iniciar-sesion?{urlencode({'error': code})}", status_code=302
    )
    clear_oauth_cookie(response)
    return response


@router.get("/google/callback", response_class=RedirectResponse, status_code=302)
def google_callback(
    request: Request,
    session: SessionDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    # Sin límite propio: sin la cookie firmada que deja /google/start (que sí está limitado)
    # no se llega a llamar a Google, y un 429 en JSON dejaría a la persona en una página rota.
    saved = oauth.load_state(request.cookies.get(OAUTH_COOKIE))
    # El state de la URL debe ser el que guardamos: impide que un tercero haga entrar a la
    # víctima con la cuenta de Google del atacante.
    if saved is None or not state or not hmac.compare_digest(state, str(saved.get("state"))):
        return _back_to_login("google_failed")
    if error:
        return _back_to_login("google_cancelled")
    if not code:
        return _back_to_login("google_failed")
    try:
        _, pair = google_login.login_with_google(
            session, code, saved["verifier"], saved["nonce"], client_ip(request)
        )
    except GoogleLoginError as exc:
        return _back_to_login(exc.code)
    response = RedirectResponse(
        f"{settings.frontend_origin}{safe_next_path(saved['next'])}", status_code=302
    )
    set_session_cookies(response, pair.access, pair.refresh)
    clear_oauth_cookie(response)
    return response


@router.get("/me", responses=_errors(401))
def me(user: CurrentUser, session: SessionDep) -> SessionUser:
    return _session_user(session, user)


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT, responses=_errors(401, 429))
@limiter.limit(lambda: settings.rate_refresh)
def refresh(request: Request, response: Response, session: SessionDep) -> None:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise NotAuthenticated()
    pair = sessions.rotate(session, token)
    set_session_cookies(response, pair.access, pair.refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, session: SessionDep) -> None:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        sessions.revoke(session, token, RevokeReason.LOGOUT)
    clear_session_cookies(response)
