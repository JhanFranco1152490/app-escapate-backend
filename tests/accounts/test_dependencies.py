import pytest
from fastapi import APIRouter, Depends

from app.accounts.dependencies import CurrentUser, require_permission
from app.accounts.permissions import PERMISSIONS
from app.core.security.cookies import ACCESS_COOKIE
from app.core.security.tokens import create_token
from tests.factories import UserAccountFactory

# El registro real está vacío; las pruebas registran un código propio.
PERMISSIONS.setdefault("tests.view", "Ver la ruta de prueba")

router = APIRouter(prefix="/api/test")


@router.get("/whoami")
def whoami(user: CurrentUser):
    return {"id": user.id}


@router.get("/guarded", dependencies=[Depends(require_permission("tests.view"))])
def guarded():
    return {"ok": True}


@pytest.fixture
def client(app, client):
    app.include_router(router)
    return client


def test_without_cookie_is_not_authenticated(client):
    response = client.get("/api/test/whoami")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


@pytest.mark.parametrize("token", ["garbage", create_token("999999", "access")])
def test_garbage_or_unknown_account_fails_authentication(client, token):
    client.cookies.set(ACCESS_COOKIE, token, path="/api/")

    response = client.get("/api/test/whoami")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_failed"


def test_a_refresh_token_is_not_an_access_token(client):
    user = UserAccountFactory()
    client.cookies.set(ACCESS_COOKIE, create_token(str(user.id), "refresh"), path="/api/")

    assert client.get("/api/test/whoami").status_code == 401


def test_an_access_token_without_a_session_is_rejected(client):
    user = UserAccountFactory()
    client.cookies.set(ACCESS_COOKIE, create_token(str(user.id), "access"), path="/api/")

    response = client.get("/api/test/whoami")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_failed"


def test_valid_cookie_returns_the_user(auth_client):
    user = UserAccountFactory()

    response = auth_client(user=user).get("/api/test/whoami")

    assert response.json() == {"id": user.id}


def test_deactivated_account_is_rejected_with_a_valid_token(auth_client):
    user = UserAccountFactory(is_active=False)

    response = auth_client(user=user).get("/api/test/whoami")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_failed"


def test_permission_granted_by_the_role_passes(auth_client):
    assert auth_client(permissions=["tests.view"]).get("/api/test/guarded").status_code == 200


def test_missing_permission_is_denied(auth_client):
    response = auth_client().get("/api/test/guarded")

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_permission_route_without_session_is_not_authenticated(client):
    assert client.get("/api/test/guarded").status_code == 401


def test_unregistered_permission_codes_fail_at_import_time():
    with pytest.raises(ValueError):
        require_permission("tests.typo")
