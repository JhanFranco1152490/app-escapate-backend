import pytest
from sqlmodel import select

from app.accounts.models import UserAccount
from app.accounts.services import password_reset
from app.accounts.services.reset_tokens import TokenPurpose, make_token
from app.common.email import EmailDeliveryError
from app.core.config import Settings, settings
from app.core.security.cookies import ACCESS_COOKIE, REFRESH_COOKIE
from app.main import create_app
from tests.accounts.helpers import DOCUMENT, login, set_cookies
from tests.factories import PASSWORD, UserAccountFactory

NEW_PASSWORD = "una frase nueva y larga"
ACCEPTED = {"detail": "Si los datos corresponden a una cuenta, enviamos un enlace a su correo."}


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(password_reset, "send_email", lambda **kwargs: calls.append(kwargs))
    return calls


@pytest.fixture
def user(session):
    return UserAccountFactory(document_number=DOCUMENT, full_name="Laura Rojas")


def request_link(client, **overrides):
    body = {"document_type": "CC", "document_number": DOCUMENT} | overrides
    return client.post("/api/auth/password-reset", json=body)


def confirm(client, token, password=NEW_PASSWORD, confirmation=None, **extra):
    body = {
        "token": token,
        "password": password,
        "password_confirmation": password if confirmation is None else confirmation,
    }
    return client.post("/api/auth/password-reset/confirm", json=body | extra)


def test_requesting_a_link_for_an_account_emails_it(csrf_client, user, sent):
    response = request_link(csrf_client, document_number="1.090.123.456")

    assert (response.status_code, response.json()) == (202, ACCEPTED)
    assert sent[0]["to"] == user.email
    assert "/restablecer-contrasena#token=" in sent[0]["context"]["link"]
    assert DOCUMENT not in str(sent[0]["context"])


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"document_number": "1090999999"}, id="unknown"),
        pytest.param({"document_type": "CE"}, id="other-type"),
        pytest.param({"document_number": "12"}, id="invalid-format"),
    ],
)
def test_unknown_documents_get_the_same_answer_and_no_email(csrf_client, user, sent, overrides):
    response = request_link(csrf_client, **overrides)

    assert (response.status_code, response.json()) == (202, ACCEPTED)
    assert sent == []


def test_inactive_accounts_get_the_same_answer_and_no_email(csrf_client, sent):
    UserAccountFactory(document_number=DOCUMENT, is_active=False)

    assert (request_link(csrf_client).json(), sent) == (ACCEPTED, [])


def test_a_provider_failure_does_not_change_the_answer(csrf_client, user, monkeypatch):
    def failing(**kwargs):
        raise EmailDeliveryError("email delivery failed with status 500")

    monkeypatch.setattr(password_reset, "send_email", failing)

    assert request_link(csrf_client).status_code == 202


@pytest.mark.parametrize(
    "body, field",
    [
        ({"document_type": "CC"}, "document_number"),
        ({"document_number": DOCUMENT}, "document_type"),
        ({"document_type": "CC", "document_number": DOCUMENT, "email": "x"}, "email"),
    ],
)
def test_invalid_request_body_is_a_validation_error(csrf_client, body, field):
    response = csrf_client.post("/api/auth/password-reset", json=body)

    assert response.status_code == 422
    assert field in response.json()["fields"]


def test_requesting_a_link_requires_csrf(client, user):
    assert request_link(client).status_code == 403


def test_requesting_links_is_rate_limited_per_ip(csrf_client, user, sent, monkeypatch):
    monkeypatch.setattr(settings, "rate_password_reset", "2/hour")

    statuses = [request_link(csrf_client).status_code for _ in range(3)]

    assert statuses == [202, 202, 429]


@pytest.mark.parametrize("purpose", [TokenPurpose.RESET, TokenPurpose.INVITATION])
def test_check_reports_purpose_and_name(csrf_client, user, purpose):
    response = csrf_client.post(
        "/api/auth/password-reset/check", json={"token": make_token(user, purpose)}
    )

    assert response.json() == {"purpose": purpose, "full_name": "Laura Rojas"}


def test_check_rejects_an_invalid_link(csrf_client):
    response = csrf_client.post("/api/auth/password-reset/check", json={"token": "garbage"})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_reset_token"


def test_check_requires_csrf(client, user):
    response = client.post(
        "/api/auth/password-reset/check", json={"token": make_token(user, TokenPurpose.RESET)}
    )

    assert response.status_code == 403


@pytest.mark.parametrize("path", ["check", "confirm"])
def test_checking_and_confirming_share_the_per_ip_limit_setting(
    csrf_client, user, monkeypatch, path
):
    monkeypatch.setattr(settings, "rate_password_reset_confirm", "2/hour")
    body = {"token": "garbage"} | (
        {"password": NEW_PASSWORD, "password_confirmation": NEW_PASSWORD}
        if path == "confirm"
        else {}
    )

    statuses = [
        csrf_client.post(f"/api/auth/password-reset/{path}", json=body).status_code
        for _ in range(3)
    ]

    assert statuses == [400, 400, 429]


def test_confirm_sets_the_password_and_signs_in(csrf_client, session, user, sent):
    response = confirm(csrf_client, make_token(user, TokenPurpose.RESET))

    assert response.status_code == 200
    assert response.json()["id"] == user.id
    assert {ACCESS_COOKIE, REFRESH_COOKIE} <= set(set_cookies(response))
    assert [call["name"] for call in sent] == ["password_changed"]


def test_a_failed_change_notice_does_not_change_the_answer(csrf_client, user, monkeypatch):
    def failing(**kwargs):
        raise EmailDeliveryError("email delivery failed with status 500")

    monkeypatch.setattr(password_reset, "send_email", failing)

    response = confirm(csrf_client, make_token(user, TokenPurpose.RESET))

    assert response.status_code == 200
    assert login(csrf_client, password=NEW_PASSWORD).status_code == 200


def test_after_a_reset_only_the_new_password_works(csrf_client, user, sent):
    confirm(csrf_client, make_token(user, TokenPurpose.RESET))

    assert login(csrf_client, password=NEW_PASSWORD).status_code == 200
    assert login(csrf_client, password=PASSWORD).status_code == 401


def test_an_invitation_creates_the_first_password_without_a_change_notice(csrf_client, sent):
    invited = UserAccountFactory(document_number=DOCUMENT, password_hash=None)

    response = confirm(csrf_client, make_token(invited, TokenPurpose.INVITATION))

    assert response.status_code == 200
    assert sent == []
    assert login(csrf_client, password=NEW_PASSWORD).status_code == 200


def test_a_different_confirmation_is_reported_on_its_field(csrf_client, session, user):
    response = confirm(
        csrf_client, make_token(user, TokenPurpose.RESET), confirmation="otra frase distinta"
    )

    assert response.status_code == 422
    assert response.json()["fields"] == {
        "password_confirmation": ["Las contraseñas no coinciden."]
    }
    assert login(csrf_client, password=PASSWORD).status_code == 200


def test_a_weak_password_is_reported_on_its_field(csrf_client, user):
    response = confirm(csrf_client, make_token(user, TokenPurpose.RESET), password="corta")

    assert response.status_code == 422
    assert list(response.json()["fields"]) == ["password"]


def test_confirm_rejects_an_invalid_link(csrf_client):
    response = confirm(csrf_client, "garbage")

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_reset_token"


def test_the_same_link_works_only_once(csrf_client, user, sent):
    token = make_token(user, TokenPurpose.RESET)
    assert confirm(csrf_client, token).status_code == 200

    assert confirm(csrf_client, token, password="otra frase muy larga").status_code == 400


def test_a_reset_ends_the_sessions_opened_before(csrf_client, user, sent):
    assert login(csrf_client).status_code == 200
    old_access = csrf_client.cookies.get(ACCESS_COOKIE)

    confirm(csrf_client, make_token(user, TokenPurpose.RESET))

    csrf_client.cookies.set(ACCESS_COOKIE, old_access, path="/api/")
    assert csrf_client.get("/api/auth/me").status_code == 401


def test_confirm_rejects_extra_fields(csrf_client, user):
    response = confirm(csrf_client, make_token(user, TokenPurpose.RESET), email="x")

    assert response.status_code == 422


def test_confirm_requires_csrf(client, user):
    assert confirm(client, make_token(user, TokenPurpose.RESET)).status_code == 403


def test_no_account_is_created_along_the_way(csrf_client, session, user, sent):
    before = len(session.exec(select(UserAccount)).all())

    request_link(csrf_client, document_number="1090999999")
    confirm(csrf_client, "garbage")

    assert len(session.exec(select(UserAccount)).all()) == before


def test_reset_errors_are_documented_with_the_common_shape():
    schema = create_app(Settings(secret_key=settings.secret_key, debug=True)).openapi()

    error_ref = {"$ref": "#/components/schemas/ErrorResponse"}
    for path in ("/api/auth/password-reset/check", "/api/auth/password-reset/confirm"):
        responses = schema["paths"][path]["post"]["responses"]
        assert responses["400"]["content"]["application/json"]["schema"] == error_ref
