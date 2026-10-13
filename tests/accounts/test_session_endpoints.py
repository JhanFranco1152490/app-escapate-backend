import pytest
from sqlmodel import select

from app.accounts.models import RefreshToken
from app.core.config import Settings, settings
from app.core.security.cookies import ACCESS_COOKIE, REFRESH_COOKIE
from app.main import create_app
from tests.accounts.helpers import DOCUMENT, login, set_cookies
from tests.factories import UserAccountFactory


@pytest.fixture
def user(session):
    return UserAccountFactory(document_number=DOCUMENT)


@pytest.fixture
def logged_in(csrf_client, user):
    assert login(csrf_client).status_code == 200
    return csrf_client


def test_me_returns_the_session(logged_in, user):
    response = logged_in.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["id"] == user.id
    assert response.json()["role"]["name"] == user.role.name


def test_me_lists_the_role_permissions_sorted(auth_client):
    response = auth_client(permissions=["quotes.view", "clients.view"]).get("/api/auth/me")

    assert response.json()["permissions"] == ["clients.view", "quotes.view"]


def test_me_without_session_is_not_authenticated(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_me_with_a_garbage_cookie_fails_authentication(client):
    client.cookies.set(ACCESS_COOKIE, "garbage", path="/api/")

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_failed"


def test_deactivating_an_account_ends_its_open_session(logged_in, session, user):
    user.is_active = False
    session.commit()

    assert logged_in.get("/api/auth/me").status_code == 401
    assert logged_in.post("/api/auth/refresh").status_code == 401


def test_refresh_rotates_both_cookies(logged_in):
    old_refresh = logged_in.cookies.get(REFRESH_COOKIE)

    response = logged_in.post("/api/auth/refresh")

    assert response.status_code == 204
    assert set(set_cookies(response)) >= {ACCESS_COOKIE, REFRESH_COOKIE}
    assert logged_in.cookies.get(REFRESH_COOKIE) != old_refresh
    assert logged_in.get("/api/auth/me").status_code == 200


def test_refresh_without_cookie_is_not_authenticated(csrf_client):
    response = csrf_client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_refresh_with_a_garbage_cookie_fails_authentication(csrf_client):
    csrf_client.cookies.set(REFRESH_COOKIE, "garbage", path="/api/auth/")

    response = csrf_client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_failed"


def test_refresh_requires_csrf(client, user):
    assert client.post("/api/auth/refresh").status_code == 403


def test_logout_revokes_the_session_and_clears_cookies(logged_in, session, user):
    refresh = logged_in.cookies.get(REFRESH_COOKIE)

    response = logged_in.post("/api/auth/logout")

    assert response.status_code == 204
    cookies = set_cookies(response)
    assert "Max-Age=0" in cookies[ACCESS_COOKIE]
    assert "Max-Age=0" in cookies[REFRESH_COOKIE]
    token = session.exec(select(RefreshToken).where(RefreshToken.user_id == user.id)).one()
    assert token.revoke_reason == "logout"
    logged_in.cookies.set(REFRESH_COOKIE, refresh, path="/api/auth/")
    assert logged_in.post("/api/auth/refresh").status_code == 401


def test_logout_also_ends_the_access_token(logged_in):
    access = logged_in.cookies.get(ACCESS_COOKIE)
    assert logged_in.get("/api/auth/me").status_code == 200

    logged_in.post("/api/auth/logout")
    logged_in.cookies.set(ACCESS_COOKIE, access, path="/api/")

    response = logged_in.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_failed"


def test_the_access_token_of_a_rotated_session_stays_valid_until_it_expires(logged_in):
    access = logged_in.cookies.get(ACCESS_COOKIE)
    assert logged_in.post("/api/auth/refresh").status_code == 204

    logged_in.cookies.set(ACCESS_COOKIE, access, path="/api/")

    assert logged_in.get("/api/auth/me").status_code == 200


def test_logout_without_session_still_succeeds(csrf_client):
    assert csrf_client.post("/api/auth/logout").status_code == 204


def test_a_fourth_login_closes_the_oldest_session(csrf_client, user):
    login(csrf_client)
    oldest = csrf_client.cookies.get(REFRESH_COOKIE)
    for _ in range(3):
        login(csrf_client)

    csrf_client.cookies.set(REFRESH_COOKIE, oldest, path="/api/auth/")

    assert csrf_client.post("/api/auth/refresh").status_code == 401


def test_a_session_closed_by_the_limit_loses_its_access_token_too(csrf_client, user):
    login(csrf_client)
    oldest = csrf_client.cookies.get(ACCESS_COOKIE)
    for _ in range(3):
        login(csrf_client)
    assert csrf_client.get("/api/auth/me").status_code == 200

    csrf_client.cookies.set(ACCESS_COOKIE, oldest, path="/api/")

    assert csrf_client.get("/api/auth/me").status_code == 401


def test_auth_errors_are_documented_with_the_common_shape():
    schema = create_app(Settings(secret_key=settings.secret_key, debug=True)).openapi()

    error_ref = {"$ref": "#/components/schemas/ErrorResponse"}
    expected = {"/api/auth/login": "post", "/api/auth/me": "get", "/api/auth/refresh": "post"}
    for path, method in expected.items():
        responses = schema["paths"][path][method]["responses"]
        assert responses["401"]["content"]["application/json"]["schema"] == error_ref
