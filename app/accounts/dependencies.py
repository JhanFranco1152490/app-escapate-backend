from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from app.accounts.models import UserAccount
from app.accounts.permissions import PERMISSIONS
from app.accounts.services.access import permissions_of_role
from app.common.errors import AuthenticationFailed, NotAuthenticated, PermissionDenied
from app.core.db import get_session
from app.core.security.cookies import ACCESS_COOKIE
from app.core.security.tokens import decode_token

SessionDep = Annotated[Session, Depends(get_session)]


def get_current_user(request: Request, session: SessionDep) -> UserAccount:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise NotAuthenticated()
    subject = decode_token(token, "access")["sub"]
    # La cuenta y su estado se leen en cada petición: una desactivación aplica de inmediato,
    # sin esperar a que venza el token.
    user = session.get(UserAccount, int(subject)) if subject.isdigit() else None
    if user is None or not user.is_active:
        raise AuthenticationFailed()
    return user


CurrentUser = Annotated[UserAccount, Depends(get_current_user)]


def require_permission(code: str) -> Callable[..., UserAccount]:
    if code not in PERMISSIONS:
        raise ValueError(f"Permiso no registrado: {code}")

    def check(user: CurrentUser, session: SessionDep) -> UserAccount:
        if code not in permissions_of_role(session, user.role_id):
            raise PermissionDenied()
        return user

    return check
