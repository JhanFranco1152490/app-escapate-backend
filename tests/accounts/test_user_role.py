import logging

import pytest
from sqlmodel import select

from app.accounts.errors import CannotChangeOwnRole, InvalidFields, LastUserManager
from app.accounts.models import LoginMethod, RefreshToken, UserAccount
from app.accounts.services import user_management
from app.accounts.services.sessions import open_session
from app.common.errors import NotFound
from tests.accounts.conftest import LEAKY_PROVIDER_MESSAGE
from tests.factories import RoleFactory, UserAccountFactory


@pytest.fixture
def actor(session, advisor_role):
    # Sin users.manage: el servicio no depende de que el endpoint revise el permiso.
    return UserAccountFactory(role=advisor_role)


def test_changing_the_role_stores_the_new_one(session, actor, advisor_role, sent):
    user = UserAccountFactory(role=advisor_role)
    other = RoleFactory()

    changed = user_management.change_role(session, actor, user.id, other.id)

    session.expire_all()
    assert changed.id == user.id
    assert session.get(UserAccount, user.id).role_id == other.id
    assert sent == []


def test_the_open_sessions_of_the_person_are_kept(session, actor, advisor_role, sent):
    user = UserAccountFactory(role=advisor_role)
    open_session(session, user, LoginMethod.DOCUMENT, "127.0.0.1")

    user_management.change_role(session, actor, user.id, RoleFactory().id)

    tokens = session.exec(select(RefreshToken).where(RefreshToken.user_id == user.id)).all()
    assert tokens and all(token.revoked_at is None for token in tokens)


def test_the_same_role_changes_nothing(session, actor, administrator_role, sent):
    user = UserAccountFactory(role=administrator_role)
    before = user.updated_at

    user_management.change_role(session, actor, user.id, administrator_role.id)

    session.refresh(user)
    assert (user.role_id, user.updated_at) == (administrator_role.id, before)
    assert sent == []


def test_an_inactive_person_can_change_role(session, actor, advisor_role, sent):
    user = UserAccountFactory(role=advisor_role, is_active=False)
    other = RoleFactory()

    user_management.change_role(session, actor, user.id, other.id)

    session.refresh(user)
    assert user.role_id == other.id


def test_nobody_changes_their_own_role(session, actor):
    with pytest.raises(CannotChangeOwnRole):
        user_management.change_role(session, actor, actor.id, RoleFactory().id)


def test_an_unknown_role_is_a_field_error(session, actor, advisor_role):
    user = UserAccountFactory(role=advisor_role)

    with pytest.raises(InvalidFields) as error:
        user_management.change_role(session, actor, user.id, 999_999_999)

    assert error.value.fields == {"role_id": ["El rol no existe."]}


def test_an_unknown_user_is_not_found(session, actor, advisor_role):
    with pytest.raises(NotFound):
        user_management.change_role(session, actor, 999_999_999, advisor_role.id)


# --- Siempre queda alguien que gestione usuarios -------------------------------------------


def test_the_last_user_manager_cannot_lose_manage_users(
    session, actor, administrator_role, advisor_role
):
    only_manager = UserAccountFactory(role=administrator_role)

    with pytest.raises(LastUserManager):
        user_management.change_role(session, actor, only_manager.id, advisor_role.id)

    session.refresh(only_manager)
    assert only_manager.role_id == administrator_role.id


def test_one_of_two_user_managers_can_lose_manage_users(
    session, actor, administrator_role, advisor_role, sent
):
    first = UserAccountFactory(role=administrator_role)
    UserAccountFactory(role=administrator_role)

    user_management.change_role(session, actor, first.id, advisor_role.id)

    session.refresh(first)
    assert first.role_id == advisor_role.id


def test_an_inactive_manager_is_not_counted_and_does_not_count(
    session, actor, administrator_role, advisor_role
):
    UserAccountFactory(role=administrator_role, is_active=False)
    only_active = UserAccountFactory(role=administrator_role)
    inactive = UserAccountFactory(role=administrator_role, is_active=False)

    # La inactiva no gestiona a nadie: cambiarla no deja a la agencia sin gestores.
    user_management.change_role(session, actor, inactive.id, advisor_role.id)
    with pytest.raises(LastUserManager):
        user_management.change_role(session, actor, only_active.id, advisor_role.id)


# --- Correo de aviso -----------------------------------------------------------------------


def test_becoming_administrator_sends_a_notice(
    session, actor, administrator_role, advisor_role, sent
):
    user = UserAccountFactory(role=advisor_role)

    user_management.change_role(session, actor, user.id, administrator_role.id)

    assert len(sent) == 1
    assert sent[0]["to"] == user.email
    assert sent[0]["name"] == "role_changed"
    assert sent[0]["subject"] == "Tu rol en Escápate cambió"
    assert sent[0]["context"] == {
        "name": user.full_name,
        "old_role": "Asesor comercial",
        "new_role": "Administrador",
    }


def test_leaving_administrator_sends_a_notice(
    session, actor, administrator_role, advisor_role, sent
):
    UserAccountFactory(role=administrator_role)
    user = UserAccountFactory(role=administrator_role)

    user_management.change_role(session, actor, user.id, advisor_role.id)

    assert [email["context"]["old_role"] for email in sent] == ["Administrador"]
    assert sent[0]["context"]["new_role"] == "Asesor comercial"


def test_a_change_between_operation_roles_sends_nothing(session, actor, advisor_role, sent):
    user = UserAccountFactory(role=advisor_role)

    user_management.change_role(session, actor, user.id, RoleFactory().id)

    assert sent == []


def test_an_inactive_person_gets_no_notice(session, actor, administrator_role, advisor_role, sent):
    user = UserAccountFactory(role=advisor_role, is_active=False)

    user_management.change_role(session, actor, user.id, administrator_role.id)

    assert sent == []


def test_a_mail_failure_keeps_the_change_and_logs_no_personal_data(
    session, actor, administrator_role, advisor_role, email_down, caplog
):
    user = UserAccountFactory(role=advisor_role)

    with caplog.at_level(logging.DEBUG):
        user_management.change_role(session, actor, user.id, administrator_role.id)

    session.refresh(user)
    assert user.role_id == administrator_role.id
    assert "EmailDeliveryError" in caplog.text
    assert LEAKY_PROVIDER_MESSAGE not in caplog.text
    assert user.email not in caplog.text
