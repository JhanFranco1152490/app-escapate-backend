import logging

import pytest
from sqlmodel import func, select

from app.accounts.errors import (
    AccountInactive,
    CannotDeactivateSelf,
    EmailDeliveryFailed,
    InvalidResetToken,
    InvitationNotPending,
    LastUserManager,
    UserInactive,
)
from app.accounts.models import LoginEvent, LoginMethod, RefreshToken, UserAccount
from app.accounts.permissions import PERMISSIONS
from app.accounts.services import google_login, user_management
from app.accounts.services.access import permissions_of_role
from app.accounts.services.google_login import GoogleLoginError, _find_account
from app.accounts.services.password_login import login_with_document
from app.accounts.services.reset_tokens import TokenPurpose, make_token, read_token
from app.accounts.services.sessions import is_session_open, open_session
from app.common.errors import NotFound
from app.core.config import settings
from app.core.security.tokens import decode_token
from tests.factories import PASSWORD, UserAccountFactory

IP = "203.0.113.9"


def revoke_reasons(session, user) -> list[str | None]:
    statement = select(RefreshToken).where(RefreshToken.user_id == user.id)
    return [token.revoke_reason for token in session.exec(statement).all()]


def deactivate(session, actor, user):
    return user_management.deactivate_user(session, actor, user.id)


def test_deactivating_blocks_the_account_without_deleting_anything(
    session, administrator_role, advisor_role
):
    actor = UserAccountFactory(role=administrator_role)
    user = UserAccountFactory(role=advisor_role)
    pair = open_session(session, user, LoginMethod.DOCUMENT, IP)
    session_id = decode_token(pair.access, "access")["sid"]

    deactivate(session, actor, user)

    saved = session.get(UserAccount, user.id)
    assert saved.is_active is False
    assert revoke_reasons(session, user) == ["account_disabled"]
    assert is_session_open(session, session_id) is False
    assert saved.email and saved.document_number and saved.password_hash
    count = select(func.count()).select_from(LoginEvent).where(LoginEvent.user_id == user.id)
    assert session.exec(count).one() == 1


def test_a_deactivated_account_cannot_enter_with_its_document(session, advisor_role):
    actor = UserAccountFactory(role=advisor_role)
    user = UserAccountFactory(document_number="52111222")

    deactivate(session, actor, user)

    with pytest.raises(AccountInactive):
        login_with_document(session, "CC", "52111222", PASSWORD, IP)


def test_a_deactivated_account_cannot_enter_with_google(session, monkeypatch):
    actor = UserAccountFactory()
    user = UserAccountFactory(google_sub="google-sub-3")
    monkeypatch.setattr(settings, "google_client_id", "cliente-de-prueba")
    monkeypatch.setattr(google_login, "_exchange_code", lambda code, verifier: "id-token")
    claims = {"sub": "google-sub-3", "email": user.email, "email_verified": True}
    monkeypatch.setattr(google_login, "_verify_id_token", lambda token, nonce: claims)

    deactivate(session, actor, user)

    with pytest.raises(GoogleLoginError) as error:
        google_login.login_with_google(session, "code", "verifier", "nonce", IP)
    assert error.value.code == "account_inactive"


def test_the_links_of_a_deactivated_account_stop_working(session):
    actor = UserAccountFactory()
    user = UserAccountFactory()
    reset_link = make_token(user, TokenPurpose.RESET)
    invitation_link = make_token(user, TokenPurpose.INVITATION)

    deactivate(session, actor, user)

    for link in (reset_link, invitation_link):
        with pytest.raises(InvalidResetToken):
            read_token(session, link)


def test_nobody_can_deactivate_their_own_account(session, administrator_role):
    actor = UserAccountFactory(role=administrator_role)
    UserAccountFactory(role=administrator_role)

    with pytest.raises(CannotDeactivateSelf):
        deactivate(session, actor, actor)

    assert session.get(UserAccount, actor.id).is_active


def test_the_last_active_user_manager_cannot_be_deactivated(
    session, administrator_role, advisor_role
):
    only_manager = UserAccountFactory(role=administrator_role)
    outsider = UserAccountFactory(role=advisor_role)

    with pytest.raises(LastUserManager):
        deactivate(session, outsider, only_manager)

    assert session.get(UserAccount, only_manager.id).is_active
    assert revoke_reasons(session, only_manager) == []


def test_one_of_two_user_managers_can_be_deactivated(session, administrator_role):
    first = UserAccountFactory(role=administrator_role)
    second = UserAccountFactory(role=administrator_role)

    deactivate(session, first, second)

    assert session.get(UserAccount, second.id).is_active is False


def test_a_manager_who_is_already_inactive_does_not_count(session, administrator_role):
    UserAccountFactory(role=administrator_role, is_active=False)
    active = UserAccountFactory(role=administrator_role)
    outsider = UserAccountFactory()

    with pytest.raises(LastUserManager):
        deactivate(session, outsider, active)


def test_a_user_without_the_manage_permission_can_be_deactivated_even_if_there_is_one_manager(
    session, administrator_role, advisor_role
):
    UserAccountFactory(role=administrator_role)
    actor = UserAccountFactory(role=administrator_role)
    advisor = UserAccountFactory(role=advisor_role)

    deactivate(session, actor, advisor)

    assert session.get(UserAccount, advisor.id).is_active is False


def test_deactivating_an_inactive_account_changes_nothing(session):
    actor = UserAccountFactory()
    user = UserAccountFactory(is_active=False)

    result = deactivate(session, actor, user)

    assert result.is_active is False and revoke_reasons(session, user) == []


def test_deactivating_an_unknown_account_is_not_found(session):
    with pytest.raises(NotFound):
        user_management.deactivate_user(session, UserAccountFactory(), 999_999_999)


def test_activating_lets_the_person_enter_again_with_their_role_permissions(
    session, administrator_role
):
    user = UserAccountFactory(role=administrator_role, document_number="52111222", is_active=False)

    user_management.activate_user(session, user.id)

    entered, _ = login_with_document(session, "CC", "52111222", PASSWORD, IP)
    assert entered.id == user.id
    assert permissions_of_role(session, entered.role_id) == sorted(PERMISSIONS)


def test_activating_an_active_account_changes_nothing(session):
    user = UserAccountFactory()

    assert user_management.activate_user(session, user.id).is_active is True


def test_activating_an_unknown_account_is_not_found(session):
    with pytest.raises(NotFound):
        user_management.activate_user(session, 999_999_999)


def test_resending_the_invitation_sends_a_new_link(session, sent):
    user = UserAccountFactory(password_hash=None)

    user_management.resend_invitation(session, user.id)

    assert [email["to"] for email in sent] == [user.email]
    assert "/crear-contrasena#token=" in sent[0]["context"]["link"]


def test_resending_works_for_someone_who_only_entered_with_google(session, sent):
    user = UserAccountFactory(password_hash=None, google_sub="google-sub-4")

    user_management.resend_invitation(session, user.id)

    assert len(sent) == 1


def test_resending_is_refused_once_the_password_exists(session, sent):
    user = UserAccountFactory()

    with pytest.raises(InvitationNotPending):
        user_management.resend_invitation(session, user.id)

    assert sent == []


def test_resending_is_refused_for_an_inactive_account(session, sent):
    user = UserAccountFactory(password_hash=None, is_active=False)

    with pytest.raises(UserInactive):
        user_management.resend_invitation(session, user.id)

    assert sent == []


def test_resending_reports_a_mail_failure_without_leaking_data(session, email_down, caplog):
    user = UserAccountFactory(password_hash=None)

    with caplog.at_level(logging.DEBUG), pytest.raises(EmailDeliveryFailed):
        user_management.resend_invitation(session, user.id)

    assert user.email not in caplog.text and "secreto@example.com" not in caplog.text


def test_resending_to_an_unknown_account_is_not_found(session):
    with pytest.raises(NotFound):
        user_management.resend_invitation(session, 999_999_999)


def test_unlinking_google_closes_the_sessions_and_allows_linking_again(session):
    user = UserAccountFactory(google_sub="google-sub-5")
    open_session(session, user, LoginMethod.GOOGLE, IP)
    open_session(session, user, LoginMethod.DOCUMENT, IP)

    result = user_management.unlink_google(session, user.id)

    assert result.google_sub is None
    assert revoke_reasons(session, user) == ["google_unlinked"] * 2
    # La próxima vez que entre con Google, se vuelve a vincular por el correo.
    assert _find_account(session, "google-sub-5", user.email).id == user.id


def test_unlinking_an_account_without_google_does_nothing(session):
    user = UserAccountFactory()
    open_session(session, user, LoginMethod.DOCUMENT, IP)

    user_management.unlink_google(session, user.id)

    assert revoke_reasons(session, user) == [None]


def test_unlinking_google_of_an_unknown_account_is_not_found(session):
    with pytest.raises(NotFound):
        user_management.unlink_google(session, 999_999_999)
