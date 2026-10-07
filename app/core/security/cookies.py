from fastapi import Response

from app.core.config import settings
from app.core.security.tokens import ACCESS_TTL, REFRESH_TTL

ACCESS_COOKIE = "escapate_access"
REFRESH_COOKIE = "escapate_refresh"
CSRF_COOKIE = "escapate_csrf"
_API_PATH = "/api/"
_AUTH_PATH = "/api/auth/"


def _flags() -> dict:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
    }


def set_session_cookies(response: Response, access: str, refresh: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        max_age=int(ACCESS_TTL.total_seconds()),
        path=_API_PATH,
        **_flags(),
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=int(REFRESH_TTL.total_seconds()),
        path=_AUTH_PATH,
        **_flags(),
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path=_API_PATH, **_flags())
    response.delete_cookie(REFRESH_COOKIE, path=_AUTH_PATH, **_flags())


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(CSRF_COOKIE, token, path=_API_PATH, **_flags())
