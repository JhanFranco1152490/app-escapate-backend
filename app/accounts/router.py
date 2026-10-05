from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.core.security.cookies import set_csrf_cookie
from app.core.security.csrf import new_csrf_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class CsrfToken(BaseModel):
    csrf_token: str


@router.get("/csrf")
def get_csrf_token(response: Response) -> CsrfToken:
    token = new_csrf_token()
    set_csrf_cookie(response, token)
    return CsrfToken(csrf_token=token)
