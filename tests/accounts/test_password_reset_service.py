import logging
from datetime import UTC, datetime

import pytest
from sqlmodel import select

from app.accounts.errors import InvalidPassword, InvalidResetToken
from app.accounts.models import LoginAttempt, LoginEvent, RefreshToken
from app.accounts.services import lockout, password_reset, sessions
from app.accounts.services.reset_tokens import TokenPurpose, make_token
from app.common.email import EmailDeliveryError
from app.core.config import settings
from app.core.security.passwords import verify_password
from tests.factories import UserAccountFactory

NEW_PASSWORD = "una frase nueva y larga"
DOCUMENT = "1090123456"
IP = "203.0.113.9"


def failing_provider(**kwargs):
    raise EmailDeliveryError("email delivery failed with status 500")


@pytest.fixture
def user(session):
    return UserAccountFactory(document_number=DOCUMENT, email="laura@example.com")


def confirm(session, user, purpose=TokenPurpose.RESET, password=NEW_PASSWORD, confirmation=None):
    token = make_token(user, purpose)
    return password_reset.confirm(
        session, token, password, password if confirmation is None else confirmation, IP
    )


def test_request_reset_prepares_the_email_for_an_active_account(session, user):
    email = password_reset.request_reset(session, "CC", "1.090.123.456")

    assert email.to == "laura@example.com"
    assert email.template == "password_reset"
    assert email.context["link"].startswith(
        f"{settings.frontend_origin}/restablecer-contrasena#token="
    )
    assert email.context["expires_in"] == "30 minutos"
    assert DOCUMENT not in str(email.context)


@pytest.mark.parametrize(
    "document_type, number",
    [("CC", "1090999999"), ("CE", DOCUMENT), ("CC", "١٠٩٠١٢٣٤٥٦"), ("CC", "12")],
)
def test_request_reset_ignores_unknown_documents(session, user, document_type, number):
    assert password_reset.request_reset(session, document_type, number) is None


def test_request_reset_ignores_inactive_accounts(session):
    UserAccountFactory(document_number=DOCUMENT, is_active=False)

    assert password_reset.request_reset(session, "CC", DOCUMENT) is None


def test_deliver_sends_the_prepared_email(session, user, sent):
    password_reset.deliver(password_reset.request_reset(session, "CC", DOCUMENT))

    assert sent[0]["to"] == "laura@example.com"
    assert sent[0]["name"] == "password_reset"


def test_deliver_logs_a_provider_failure_without_the_address(session, user, monkeypatch, caplog):
    monkeypatch.setattr(password_reset, "send_email", failing_provider)
    email = password_reset.request_reset(session, "CC", DOCUMENT)

    with caplog.at_level(logging.WARNING):
        password_reset.deliver(email)

    assert "EmailDeliveryError" in caplog.text
    assert "laura@example.com" not in caplog.text


def test_send_invitation_sends_the_create_password_link(session, sent):
    invited = UserAccountFactory(password_hash=None)

    password_reset.send_invitation(invited)

    assert sent[0]["name"] == "invitation"
    assert sent[0]["context"]["link"].startswith(
        f"{settings.frontend_origin}/crear-contrasena#token="
    )
    assert sent[0]["context"]["expires_in"] == "72 horas"


def test_send_invitation_lets_the_caller_know_it_failed(session, monkeypatch):
    monkeypatch.setattr(password_reset, "send_email", failing_provider)

    with pytest.raises(EmailDeliveryError):
        password_reset.send_invitation(UserAccountFactory())


def test_confirm_sets_the_password_and_opens_a_session(session, user):
    result = confirm(session, user)

    assert result.user == user
    assert verify_password(NEW_PASSWORD, user.password_hash)[0]
    event = session.exec(select(LoginEvent).where(LoginEvent.user_id == user.id)).one()
    assert event.method == "email_link"
    assert result.pair.access and result.pair.refresh


def test_confirm_closes_every_previous_session(session, user):
    sessions.open_session(session, user, "document", IP)
    session.commit()

    confirm(session, user)

    reasons = {
        token.revoke_reason
        for token in session.exec(select(RefreshToken).where(RefreshToken.user_id == user.id))
    }
    assert "password_changed" in reasons


def test_confirm_clears_the_document_locks_in_every_ip(session, user):
    identifier = lockout.lock_identifier("CC", DOCUMENT)
    for _ in range(lockout.MAX_FAILURES):
        lockout.register_failure(session, identifier, "198.51.100.1", datetime.now(UTC))
    session.commit()

    confirm(session, user)

    assert session.exec(select(LoginAttempt)).first() is None


def test_a_reset_returns_the_change_notice_and_an_invitation_does_not(session, user):
    reset = confirm(session, user)
    invited = UserAccountFactory(password_hash=None)
    invitation = confirm(session, invited, TokenPurpose.INVITATION)

    assert reset.notice.template == "password_changed"
    assert reset.notice.to == "laura@example.com"
    assert "link" not in reset.notice.context
    assert invitation.notice is None


def test_a_different_confirmation_changes_nothing(session, user):
    old_hash = user.password_hash

    with pytest.raises(InvalidPassword) as error:
        confirm(session, user, confirmation="otra frase distinta")

    assert error.value.fields == {"password_confirmation": ["Las contraseñas no coinciden."]}
    session.refresh(user)
    assert user.password_hash == old_hash


@pytest.mark.parametrize("password", ["corta", "laura@example.com"])
def test_the_password_policy_applies(session, user, password):
    with pytest.raises(InvalidPassword) as error:
        confirm(session, user, password=password)

    assert list(error.value.fields) == ["password"]


def test_both_problems_are_reported_together(session, user):
    with pytest.raises(InvalidPassword) as error:
        confirm(session, user, password="corta", confirmation="otra")

    assert set(error.value.fields) == {"password", "password_confirmation"}


def test_an_invalid_token_is_rejected_before_looking_at_the_password(session, user):
    with pytest.raises(InvalidResetToken):
        password_reset.confirm(session, "garbage", "corta", "otra", IP)


def test_the_same_link_works_only_once(session, user):
    token = make_token(user, TokenPurpose.RESET)
    password_reset.confirm(session, token, NEW_PASSWORD, NEW_PASSWORD, IP)

    with pytest.raises(InvalidResetToken):
        password_reset.confirm(session, token, "otra frase muy larga", "otra frase muy larga", IP)


def test_an_invited_account_ends_up_with_a_password(session):
    invited = UserAccountFactory(password_hash=None)

    confirm(session, invited, TokenPurpose.INVITATION)

    assert verify_password(NEW_PASSWORD, invited.password_hash)[0]
