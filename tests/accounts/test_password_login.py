from datetime import UTC, datetime, timedelta

import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlmodel import select

from app.accounts.models import LoginAttempt, LoginEvent, RefreshToken
from app.accounts.services.lockout import (
    ANY_IP,
    FAILURE_WINDOW,
    MAX_FAILURES,
    MAX_FAILURES_ANY_IP,
)
from app.core.config import settings
from tests.accounts.helpers import DOCUMENT, login, set_cookies
from tests.factories import PASSWORD, UserAccountFactory

INVALID = {
    "detail": "El documento o la contraseña no son válidos.",
    "code": "invalid_credentials",
    "fields": {},
}


@pytest.fixture
def user(session):
    return UserAccountFactory(document_type="CC", document_number=DOCUMENT)


def pair_attempt(session) -> LoginAttempt:
    session.expire_all()
    return session.exec(select(LoginAttempt).where(LoginAttempt.ip != ANY_IP)).one()


def document_attempt(session) -> LoginAttempt:
    session.expire_all()
    return session.exec(select(LoginAttempt).where(LoginAttempt.ip == ANY_IP)).one()


def test_valid_credentials_open_a_session(csrf_client, session, user):
    response = login(csrf_client)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": {"id": user.role_id, "name": user.role.name},
        "permissions": [],
    }
    cookies = set_cookies(response)
    assert "Path=/api/" in cookies["escapate_access"]
    assert "Path=/api/auth/" in cookies["escapate_refresh"]
    assert all("HttpOnly" in cookie for cookie in cookies.values() if "escapate_" in cookie)
    assert session.exec(select(RefreshToken).where(RefreshToken.user_id == user.id)).one()
    event = session.exec(select(LoginEvent).where(LoginEvent.user_id == user.id)).one()
    assert event.method == "document"


def test_the_session_never_includes_the_document(csrf_client, user):
    assert DOCUMENT not in login(csrf_client).text


@pytest.mark.parametrize("number", ["1.090.123.456", " 1090-123-456 "])
def test_document_with_separators_logs_in(csrf_client, user, number):
    assert login(csrf_client, document_number=number).status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"password": "otra-contrasena-123"}, id="wrong-password"),
        pytest.param({"document_number": "1090999999"}, id="unknown-document"),
        pytest.param({"document_type": "CE"}, id="right-number-wrong-type"),
        pytest.param({"document_number": "١٠٩٠١٢٣٤٥٦"}, id="other-alphabet-digits"),
    ],
)
def test_wrong_credentials_get_the_same_answer(csrf_client, user, overrides):
    response = login(csrf_client, **overrides)

    assert response.status_code == 401
    assert response.json() == INVALID


def test_account_without_password_gets_the_same_answer(csrf_client):
    UserAccountFactory(document_number=DOCUMENT, password_hash=None)

    response = login(csrf_client)

    assert (response.status_code, response.json()) == (401, INVALID)


def test_inactive_account_with_the_right_password_is_told_so(csrf_client):
    UserAccountFactory(document_number=DOCUMENT, is_active=False)

    response = login(csrf_client)

    assert response.status_code == 403
    assert response.json()["code"] == "account_inactive"
    assert "escapate_access" not in set_cookies(response)


def test_inactive_account_with_a_wrong_password_does_not_reveal_it(csrf_client):
    UserAccountFactory(document_number=DOCUMENT, is_active=False)

    response = login(csrf_client, password="otra-contrasena-123")

    assert (response.status_code, response.json()) == (401, INVALID)


@pytest.mark.parametrize(
    "body, field",
    [
        pytest.param(
            {"document_type": "CC", "password": PASSWORD}, "document_number", id="no-doc"
        ),
        pytest.param(
            {"document_type": "CC", "document_number": DOCUMENT}, "password", id="no-pwd"
        ),
        pytest.param(
            {"document_number": DOCUMENT, "password": PASSWORD}, "document_type", id="no-type"
        ),
        pytest.param(
            {"document_type": "CC", "document_number": "   ", "password": PASSWORD},
            "document_number",
            id="blank-doc",
        ),
        pytest.param(
            {"document_type": "CC", "document_number": DOCUMENT, "password": ""},
            "password",
            id="empty-pwd",
        ),
        pytest.param(
            {"document_type": "CC", "document_number": DOCUMENT, "password": "a" * 257},
            "password",
            id="long-pwd",
        ),
        pytest.param(
            {"document_type": "CC", "document_number": "1" * 31, "password": PASSWORD},
            "document_number",
            id="long-doc",
        ),
        pytest.param(
            {"document_type": "NIT", "document_number": DOCUMENT, "password": PASSWORD},
            "document_type",
            id="unknown-type",
        ),
        pytest.param(
            {"document_type": "CC", "document_number": DOCUMENT, "password": PASSWORD, "x": 1},
            "x",
            id="extra-field",
        ),
    ],
)
def test_invalid_body_is_a_validation_error(csrf_client, body, field):
    response = csrf_client.post("/api/auth/login", json=body)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert field in response.json()["fields"]


def fail(client, times: int, **headers) -> None:
    for _ in range(times):
        response = client.post(
            "/api/auth/login",
            json={"document_type": "CC", "document_number": DOCUMENT, "password": "mala-123456"},
            headers=headers,
        )
        assert response.status_code == 401


def test_five_failures_lock_the_document_even_with_the_right_password(csrf_client, user):
    fail(csrf_client, 5)

    response = login(csrf_client)

    assert response.status_code == 429
    assert response.json()["code"] == "account_locked"


def test_the_lock_is_per_ip(csrf_client, user, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    fail(csrf_client, 5, **{"X-Forwarded-For": "198.51.100.1"})

    response = csrf_client.post(
        "/api/auth/login",
        json={"document_type": "CC", "document_number": DOCUMENT, "password": PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.2"},
    )

    assert response.status_code == 200


def fail_from_many_ips(client, ips: int, per_ip: int):
    for number in range(ips):
        fail(client, per_ip, **{"X-Forwarded-For": f"198.51.100.{number + 1}"})


def login_from(client, ip: str):
    return client.post(
        "/api/auth/login",
        json={"document_type": "CC", "document_number": DOCUMENT, "password": PASSWORD},
        headers={"X-Forwarded-For": ip},
    )


def test_failures_from_many_ips_lock_the_document(csrf_client, user, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    fail_from_many_ips(csrf_client, MAX_FAILURES_ANY_IP // (MAX_FAILURES - 1), MAX_FAILURES - 1)

    response = login_from(csrf_client, "198.51.100.200")

    assert response.status_code == 429
    assert response.json()["code"] == "account_locked"


def test_failures_from_many_ips_below_the_total_do_not_lock(csrf_client, user, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    fail_from_many_ips(
        csrf_client, MAX_FAILURES_ANY_IP // (MAX_FAILURES - 1) - 1, MAX_FAILURES - 1
    )

    assert login_from(csrf_client, "198.51.100.200").status_code == 200


def test_a_successful_login_keeps_the_count_across_ips(csrf_client, session, user):
    fail(csrf_client, 3)

    assert login(csrf_client).status_code == 200

    assert document_attempt(session).failures == 3
    assert session.exec(select(LoginAttempt).where(LoginAttempt.ip != ANY_IP)).first() is None


def test_old_failures_stop_counting(csrf_client, session, user):
    fail(csrf_client, MAX_FAILURES - 1)
    for attempt in session.exec(select(LoginAttempt)).all():
        attempt.updated_at = datetime.now(UTC) - FAILURE_WINDOW - timedelta(seconds=1)
    session.commit()

    fail(csrf_client, MAX_FAILURES - 1)

    assert pair_attempt(session).failures == MAX_FAILURES - 1
    assert document_attempt(session).failures == MAX_FAILURES - 1
    assert login(csrf_client).status_code == 200


def test_after_the_lock_expires_the_account_can_log_in(csrf_client, session, user):
    fail(csrf_client, 5)
    attempt = pair_attempt(session)
    attempt.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()

    assert login(csrf_client).status_code == 200


def test_a_failure_after_an_expired_lock_starts_counting_again(csrf_client, session, user):
    fail(csrf_client, 5)
    attempt = pair_attempt(session)
    attempt.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()

    fail(csrf_client, 1)

    session.refresh(attempt)
    assert (attempt.failures, attempt.locked_until) == (1, None)


def test_a_successful_login_resets_the_failures(csrf_client, session, user):
    fail(csrf_client, 4)
    assert login(csrf_client).status_code == 200

    fail(csrf_client, 4)

    assert login(csrf_client).status_code == 200


def test_login_attempt_never_stores_the_document(csrf_client, session, user):
    fail(csrf_client, 1)

    for attempt in session.exec(select(LoginAttempt)).all():
        assert DOCUMENT not in attempt.identifier
        assert len(attempt.identifier) == 64


def test_an_outdated_hash_is_replaced_on_login(csrf_client, session):
    weak = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8192),))
    old_hash = weak.hash(PASSWORD)
    user = UserAccountFactory(document_number=DOCUMENT, password_hash=old_hash)

    assert login(csrf_client).status_code == 200

    session.refresh(user)
    assert user.password_hash != old_hash


def test_login_requires_csrf(client, user):
    assert login(client).status_code == 403


def test_login_is_rate_limited_per_ip(csrf_client, user, monkeypatch):
    monkeypatch.setattr(settings, "rate_login", "2/minute")

    statuses = [login(csrf_client).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]
