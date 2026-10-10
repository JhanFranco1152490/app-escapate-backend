from urllib.parse import parse_qs, urlparse

import httpx2
import pytest
from sqlmodel import func, select

from app.accounts.models import LoginEvent, UserAccount
from app.accounts.services import google_login
from app.core.config import settings
from app.core.security.cookies import ACCESS_COOKIE, OAUTH_COOKIE, REFRESH_COOKIE
from app.core.security.oauth import dump_state
from tests.accounts.google import (
    CLIENT_ID,
    GOOGLE_KEY,
    OMIT,
    OTHER_KEY,
    FakeGoogle,
    callback,
    make_id_token,
    redirect_error,
    start,
)
from tests.accounts.helpers import set_cookies
from tests.factories import UserAccountFactory


@pytest.fixture
def google(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "google_client_secret", "secreto-de-prueba")
    monkeypatch.setattr(google_login, "_http_client", fake.client)
    monkeypatch.setattr(google_login, "_signing_key", lambda token: GOOGLE_KEY.public_key())
    return fake


def sign_in(client, google, next_path="/clientes", **claims):
    _, state, nonce = start(client, next_path)
    google.id_token = make_id_token(nonce, **claims)
    return callback(client, code="codigo-de-google", state=state)


def test_start_redirects_to_google_with_pkce_and_account_chooser(client, google):
    response, _, _ = start(client)

    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    query = {name: values[0] for name, values in parse_qs(location.query).items()}
    assert location.netloc == "accounts.google.com"
    assert query["client_id"] == CLIENT_ID
    assert query["redirect_uri"] == settings.google_redirect_uri
    assert query["response_type"] == "code"
    assert query["scope"] == "openid email profile"
    assert query["code_challenge_method"] == "S256"
    assert query["prompt"] == "select_account"
    oauth_cookie = set_cookies(response)[OAUTH_COOKIE]
    assert "Path=/api/auth/google/" in oauth_cookie and "HttpOnly" in oauth_cookie


def test_linked_account_signs_in_and_returns_to_next(client, google, session):
    user = UserAccountFactory(google_sub="google-sub-1")

    response = sign_in(client, google)

    assert response.status_code == 302
    assert response.headers["location"] == f"{settings.frontend_origin}/clientes"
    cookies = set_cookies(response)
    assert {ACCESS_COOKIE, REFRESH_COOKIE} <= set(cookies)
    assert "Max-Age=0" in cookies[OAUTH_COOKIE]
    event = session.exec(select(LoginEvent).where(LoginEvent.user_id == user.id)).one()
    assert event.method == "google"


def test_the_code_is_exchanged_with_the_pkce_verifier(client, google):
    UserAccountFactory(google_sub="google-sub-1")

    sign_in(client, google)

    form = parse_qs(google.requests[0].content.decode())
    assert form["code"] == ["codigo-de-google"]
    assert form["grant_type"] == ["authorization_code"]
    assert form["client_id"] == [CLIENT_ID]
    assert len(form["code_verifier"][0]) >= 43


def test_first_google_login_links_the_registered_email(client, google, session):
    user = UserAccountFactory(email="persona@example.com", google_sub=None)

    response = sign_in(client, google, email="Persona@Example.com")

    assert redirect_error(response) is None
    session.refresh(user)
    assert user.google_sub == "google-sub-1"


def test_an_email_already_linked_to_another_google_account_is_not_taken(client, google, session):
    user = UserAccountFactory(email="persona@example.com", google_sub="otra-cuenta")

    response = sign_in(client, google)

    assert redirect_error(response) == "account_not_registered"
    session.refresh(user)
    assert user.google_sub == "otra-cuenta"


def test_unregistered_google_account_creates_nothing(client, google, session):
    before = session.exec(select(func.count()).select_from(UserAccount)).one()

    response = sign_in(client, google, email="desconocida@example.com")

    assert response.headers["location"].startswith(f"{settings.frontend_origin}/iniciar-sesion")
    assert redirect_error(response) == "account_not_registered"
    assert session.exec(select(func.count()).select_from(UserAccount)).one() == before
    assert ACCESS_COOKIE not in set_cookies(response)


def test_inactive_account_is_told_so_and_not_linked(client, google, session):
    user = UserAccountFactory(email="persona@example.com", google_sub=None, is_active=False)

    response = sign_in(client, google)

    assert redirect_error(response) == "account_inactive"
    session.refresh(user)
    assert user.google_sub is None


def test_external_next_is_replaced_by_the_home_page(client, google):
    UserAccountFactory(google_sub="google-sub-1")

    response = sign_in(client, google, next_path="//evil.example")

    assert response.headers["location"] == f"{settings.frontend_origin}/"


def test_a_different_state_is_rejected(client, google):
    UserAccountFactory(google_sub="google-sub-1")
    _, _, nonce = start(client)
    google.id_token = make_id_token(nonce)

    response = callback(client, code="codigo", state="otro-state")

    assert redirect_error(response) == "google_failed"
    assert google.requests == []


def test_a_callback_without_the_cookie_is_rejected(client, google):
    _, state, _ = start(client)
    client.cookies.clear()

    assert redirect_error(callback(client, code="codigo", state=state)) == "google_failed"


def test_a_cookie_with_someone_elses_state_is_rejected(client, google):
    forged = dump_state({"state": "s", "nonce": "n", "verifier": "v", "next": "/"})
    client.cookies.set(OAUTH_COOKIE, forged + "alterada", path="/api/auth/google/")

    assert redirect_error(callback(client, code="codigo", state="s")) == "google_failed"


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"key": OTHER_KEY}, id="other-signing-key"),
        pytest.param({"aud": "otro-cliente"}, id="other-audience"),
        pytest.param({"iss": "https://evil.example"}, id="other-issuer"),
        pytest.param({"exp": 1_000_000_000}, id="expired"),
        pytest.param({"nonce": "otro-nonce"}, id="other-nonce"),
        pytest.param({"email_verified": False}, id="email-not-verified"),
        pytest.param({"email_verified": OMIT}, id="email-verified-missing"),
        pytest.param({"sub": OMIT}, id="without-sub"),
    ],
)
def test_an_invalid_id_token_is_rejected(client, google, claims):
    UserAccountFactory(email="persona@example.com", google_sub="google-sub-1")
    _, state, nonce = start(client)
    claims = dict(claims)
    google.id_token = make_id_token(claims.pop("nonce", nonce), **claims)

    response = callback(client, code="codigo", state=state)

    assert redirect_error(response) == "google_failed"
    assert ACCESS_COOKIE not in set_cookies(response)


@pytest.mark.parametrize(
    "breakdown",
    [
        pytest.param({"status": 500}, id="token-endpoint-error"),
        pytest.param({"error": httpx2.ConnectError}, id="unreachable"),
        pytest.param({"error": httpx2.ReadTimeout}, id="timeout"),
        pytest.param({"id_token": None}, id="without-id-token"),
    ],
)
def test_google_failures_are_reported_as_google_failed(client, google, breakdown):
    UserAccountFactory(google_sub="google-sub-1")
    _, state, nonce = start(client)
    google.id_token = make_id_token(nonce)
    for name, value in breakdown.items():
        setattr(google, name, value)

    assert redirect_error(callback(client, code="codigo", state=state)) == "google_failed"


def test_cancelling_in_google_is_reported_as_cancelled(client, google):
    _, state, _ = start(client)

    response = callback(client, error="access_denied", state=state)

    assert redirect_error(response) == "google_cancelled"
    assert "Max-Age=0" in set_cookies(response)[OAUTH_COOKIE]


def test_without_google_configuration_the_login_fails_cleanly(client, google, monkeypatch):
    UserAccountFactory(google_sub="google-sub-1")
    monkeypatch.setattr(settings, "google_client_id", "")

    assert redirect_error(sign_in(client, google)) == "google_failed"


def test_start_is_rate_limited(client, google, monkeypatch):
    monkeypatch.setattr(settings, "rate_google", "1/minute")

    first = client.get("/api/auth/google/start", follow_redirects=False)
    second = client.get("/api/auth/google/start", follow_redirects=False)

    assert (first.status_code, second.status_code) == (302, 429)
