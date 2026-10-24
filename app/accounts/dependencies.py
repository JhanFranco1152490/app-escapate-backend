from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from app.accounts.models import UserAccount
from app.accounts.permissions import PERMISSIONS
from app.accounts.services.access import permissions_of_role
from app.accounts.services.sessions import is_session_open
from app.common.errors import AuthenticationFailed, NotAuthenticated, PermissionDenied
from app.core.db import get_session
from app.core.security.cookies import ACCESS_COOKIE
from app.core.security.tokens import decode_token

SessionDep = Annotated[Session, Depends(get_session)]


def get_current_user(request: Request, session: SessionDep) -> UserAccount:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise NotAuthenticated()
    payload = decode_token(token, "access")
    subject, session_id = payload["sub"], payload.get("sid")
    # La cuenta y su sesión se leen en cada petición: una desactivación o un cierre de sesión
    # aplican de inmediato, sin esperar a que venza el token.
    user = session.get(UserAccount, int(subject)) if subject.isdigit() else None
    if user is None or not user.is_active:
        raise AuthenticationFailed()
    if not session_id or not is_session_open(session, session_id):
        raise AuthenticationFailed()
    return user


CurrentUser = Annotated[UserAccount, Depends(get_current_user)]


def require_permission(code: str) -> Callable[..., UserAccount]:
    return require_any_permission(code)


def require_any_permission(*codes: str) -> Callable[..., UserAccount]:
    if not codes:
        raise ValueError("Se necesita al menos un código de permiso.")
    unknown = [code for code in codes if code not in PERMISSIONS]
    if unknown:
        raise ValueError(f"Permiso no registrado: {', '.join(unknown)}")

    def check(user: CurrentUser, session: SessionDep) -> UserAccount:
        if not set(codes) & set(permissions_of_role(session, user.role_id)):
            raise PermissionDenied()
        return user

    return check
