import logging

import pytest
from sqlmodel import func, select

from app.accounts.errors import DuplicateUser, InvalidFields, InvalidResetToken
from app.accounts.models import LoginMethod, RefreshToken, Role, UserAccount
from app.accounts.schemas import UserCreate, UserInput
from app.accounts.services import user_management
from app.accounts.services.password_login import find_by_document
from app.accounts.services.reset_tokens import TokenPurpose, make_token, read_token
from app.accounts.services.sessions import open_session
from app.common.errors import NotFound
from tests.accounts.conftest import LEAKY_PROVIDER_MESSAGE
from tests.factories import UserAccountFactory

NEW = {
    "first_name": "Laura",
    "last_name": "Rojas",
    "email": "laura.rojas@gmail.com",
    "document_type": "CC",
    "document_number": "1090123456",
    "phone": "3001234567",
}


@pytest.fixture
def role(session):
    return session.exec(select(Role).where(Role.name == "Asesor comercial")).one()


def count_accounts(session) -> int:
    return session.exec(select(func.count()).select_from(UserAccount)).one()


def create(session, role, **overrides):
    return user_management.create_user(session, UserCreate(**NEW | overrides, role_id=role.id))


def invitation_token(email: dict) -> str:
    return email["context"]["link"].split("#token=", 1)[1]


def test_creating_a_user_makes_an_active_account_without_password_and_invites_them(
    session, role, sent
):
    result = create(session, role)

    user = session.get(UserAccount, result.user.id)
    assert (user.first_name, user.last_name, user.email) == ("Laura", "Rojas", NEW["email"])
    assert (user.document_type, user.document_number, user.phone) == (
        "CC",
        "1090123456",
        "3001234567",
    )
    assert user.role_id == role.id
    assert user.is_active and user.password_hash is None and user.google_sub is None
    assert result.invitation_sent is True
    assert [email["to"] for email in sent] == [NEW["email"]]
    assert "/crear-contrasena#token=" in sent[0]["context"]["link"]


def test_the_invitation_link_works_and_never_carries_the_document(session, role, sent):
    result = create(session, role)

    user, purpose = read_token(session, invitation_token(sent[0]))

    assert (user.id, purpose) == (result.user.id, TokenPurpose.INVITATION)
    assert NEW["document_number"] not in str(sent)


def test_the_role_must_exist(session, sent):
    with pytest.raises(InvalidFields) as error:
        user_management.create_user(session, UserCreate(**NEW, role_id=999_999_999))

    assert error.value.fields == {"role_id": ["El rol no existe."]}
    assert sent == []


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"email": "Laura.Rojas@Gmail.com"}, "email"),
        ({"document_number": "1.090.123.456"}, "document_number"),
        ({"phone": "+57 300 123 4567"}, "phone"),
    ],
)
def test_repeated_data_is_rejected_whatever_its_format(session, role, sent, overrides, field):
    UserAccountFactory(
        email=NEW["email"], document_number=NEW["document_number"], phone=NEW["phone"]
    )
    # Cada caso repite solo un dato: el resto se cambia para que no choque.
    other = {"email": "otra@gmail.com", "document_number": "52111222", "phone": "3119998877"}
    data = NEW | {key: value for key, value in other.items() if key != field} | overrides
    before = count_accounts(session)

    with pytest.raises(DuplicateUser) as error:
        user_management.create_user(session, UserCreate(**data, role_id=role.id))

    assert list(error.value.fields) == [field]
    assert count_accounts(session) == before and sent == []


def test_all_the_repeated_fields_are_reported_together(session, role):
    UserAccountFactory(
        email=NEW["email"], document_number=NEW["document_number"], phone=NEW["phone"]
    )

    with pytest.raises(DuplicateUser) as error:
        create(session, role)

    assert set(error.value.fields) == {"email", "document_number", "phone"}


def test_the_same_number_with_another_document_type_is_a_different_person(session, role, sent):
    UserAccountFactory(document_type="CC", document_number="1090123456")

    result = create(session, role, document_type="PA")

    assert result.user.document_type == "PA" and result.invitation_sent is True


@pytest.mark.parametrize(
    "field, constraint_value",
    [
        ("email", {"email": NEW["email"]}),
        ("document_number", {"document_number": NEW["document_number"]}),
        ("phone", {"phone": NEW["phone"]}),
    ],
)
def test_the_database_constraint_answers_the_same_when_two_creations_race(
    session, role, sent, monkeypatch, field, constraint_value
):
    """Si dos altas pasan la revisión previa a la vez, la restricción única responde igual."""
    UserAccountFactory(**constraint_value)
    monkeypatch.setattr(user_management, "_duplicate_fields", lambda *args, **kwargs: [])
    other = {"email": "otra@gmail.com", "document_number": "52111222", "phone": "3119998877"}
    data = NEW | {key: value for key, value in other.items() if key != field}

    with pytest.raises(DuplicateUser) as error:
        user_management.create_user(session, UserCreate(**data, role_id=role.id))

    assert list(error.value.fields) == [field]
    assert sent == []


def test_a_mail_failure_keeps_the_account_and_says_so(session, role, email_down, caplog):
    with caplog.at_level(logging.DEBUG):
        result = create(session, role)

    assert result.invitation_sent is False
    assert session.get(UserAccount, result.user.id) is not None
    for secret in (NEW["email"], NEW["document_number"], NEW["phone"], "secreto@example.com"):
        assert secret not in caplog.text
    assert "EmailDeliveryError" in caplog.text
    assert LEAKY_PROVIDER_MESSAGE not in caplog.text


def pending_user(**overrides):
    """Una persona invitada que todavía no creó su contraseña."""
    return UserAccountFactory(password_hash=None, **overrides)


def update(session, user, **overrides):
    return user_management.update_user(session, user.id, UserInput(**NEW | overrides))


def test_editing_saves_every_editable_field(session):
    user = UserAccountFactory()

    result = update(session, user, first_name="Lucía", phone="3150000000")

    saved = session.get(UserAccount, user.id)
    assert (saved.first_name, saved.last_name, saved.phone) == ("Lucía", "Rojas", "3150000000")
    assert (saved.email, saved.document_number) == (NEW["email"], NEW["document_number"])
    assert result.invitation_sent is None


def test_the_person_enters_with_the_corrected_document(session):
    user = UserAccountFactory(document_number="52111222")

    update(session, user)

    assert find_by_document(session, "CC", "52111222") is None
    assert find_by_document(session, "CC", "1090123456").id == user.id


def test_editing_with_the_same_data_does_not_count_as_a_duplicate(session):
    user = UserAccountFactory(
        email=NEW["email"], document_number=NEW["document_number"], phone=NEW["phone"]
    )

    assert update(session, user).user.id == user.id


def test_editing_cannot_take_what_another_account_has(session):
    user = UserAccountFactory()
    UserAccountFactory(email=NEW["email"], phone=NEW["phone"])

    with pytest.raises(DuplicateUser) as error:
        update(session, user)

    assert set(error.value.fields) == {"email", "phone"}


def test_editing_does_not_change_role_or_status(session, role):
    user = UserAccountFactory(is_active=False)
    original_role = user.role_id

    update(session, user)

    saved = session.get(UserAccount, user.id)
    assert (saved.role_id, saved.is_active) == (original_role, False)


def test_editing_an_unknown_account_is_not_found(session):
    with pytest.raises(NotFound):
        user_management.update_user(session, 999_999_999, UserInput(**NEW))


def test_changing_the_email_unlinks_google_and_closes_the_sessions(session):
    user = UserAccountFactory(google_sub="google-sub-9")
    open_session(session, user, LoginMethod.GOOGLE, "10.0.0.1")
    open_session(session, user, LoginMethod.DOCUMENT, "10.0.0.1")

    result = update(session, user)

    assert result.user.google_sub is None and result.invitation_sent is None
    tokens = session.exec(select(RefreshToken).where(RefreshToken.user_id == user.id)).all()
    assert [token.revoke_reason for token in tokens] == ["google_unlinked"] * 2


def test_changing_the_email_of_an_account_without_google_keeps_its_sessions(session, sent):
    user = UserAccountFactory()
    open_session(session, user, LoginMethod.DOCUMENT, "10.0.0.1")

    update(session, user)

    token = session.exec(select(RefreshToken).where(RefreshToken.user_id == user.id)).one()
    assert token.revoked_at is None and sent == []


def test_changing_the_email_of_a_pending_invitation_sends_a_new_one(session, sent):
    user = pending_user()
    old_token = make_token(user, TokenPurpose.INVITATION)

    result = update(session, user)

    assert result.invitation_sent is True
    assert [email["to"] for email in sent] == [NEW["email"]]
    new_user, purpose = read_token(session, invitation_token(sent[0]))
    assert (new_user.id, purpose) == (user.id, TokenPurpose.INVITATION)
    with pytest.raises(InvalidResetToken):
        read_token(session, old_token)


def test_no_invitation_for_an_inactive_account(session, sent):
    """Su enlace no serviría: las cuentas inactivas no pueden crear la contraseña."""
    result = update(session, pending_user(is_active=False))

    assert result.invitation_sent is None and sent == []


def test_an_edit_that_does_not_change_the_email_sends_nothing(session, sent):
    user = pending_user(email=NEW["email"])

    result = update(session, user, first_name="Lucía")

    assert result.invitation_sent is None and sent == []


def test_a_mail_failure_on_edit_keeps_the_changes(session, email_down):
    user = pending_user()

    result = update(session, user)

    assert result.invitation_sent is False
    assert session.get(UserAccount, user.id).email == NEW["email"]
