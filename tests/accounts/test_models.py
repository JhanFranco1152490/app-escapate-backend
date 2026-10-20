import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.accounts.models import LoginEvent, Role, UserAccount
from tests.factories import RoleFactory, UserAccountFactory

SEEDED_ROLES = {"Administrador", "Asesor comercial", "Encargado de proveedores", "Operativo"}


def test_migration_seeds_the_four_roles(session):
    names = set(session.exec(select(Role.name)).all())

    assert SEEDED_ROLES <= names


def test_email_is_unique(session):
    UserAccountFactory(email="ana@example.com")

    with pytest.raises(IntegrityError):
        UserAccountFactory(email="ana@example.com")


def test_document_is_unique_per_type(session):
    UserAccountFactory(document_type="CC", document_number="10900001")

    with pytest.raises(IntegrityError):
        UserAccountFactory(document_type="CC", document_number="10900001")


def test_same_number_with_another_type_is_another_person(session):
    UserAccountFactory(document_type="CC", document_number="10900001")

    UserAccountFactory(document_type="PA", document_number="10900001")


def test_google_sub_is_unique(session):
    UserAccountFactory(google_sub="google-123")

    with pytest.raises(IntegrityError):
        UserAccountFactory(google_sub="google-123")


def test_unknown_document_type_is_rejected(session):
    with pytest.raises(IntegrityError):
        UserAccountFactory(document_type="NIT")


def test_a_role_with_accounts_cannot_be_deleted(session):
    role = RoleFactory()
    UserAccountFactory(role=role)

    session.delete(role)
    with pytest.raises(IntegrityError):
        session.flush()


def test_login_event_method_is_restricted(session):
    user = UserAccountFactory()

    session.add(LoginEvent(user_id=user.id, method="facebook", ip="127.0.0.1"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_new_accounts_are_active_without_password_or_google(session):
    role = RoleFactory()
    user = UserAccount(
        email="nuevo@example.com",
        first_name="Persona",
        last_name="Nueva",
        document_type="CC",
        document_number="10900002",
        role_id=role.id,
    )
    session.add(user)
    session.flush()

    assert user.is_active is True
    assert user.password_hash is None
    assert user.google_sub is None


def test_login_event_accepts_sessions_opened_from_an_email_link(session):
    user = UserAccountFactory()

    session.add(LoginEvent(user_id=user.id, method="email_link", ip="127.0.0.1"))
    session.flush()


def test_full_name_joins_first_and_last_name_without_a_trailing_space():
    assert (
        UserAccount(first_name="Laura", last_name="Rojas Pérez").full_name == "Laura Rojas Pérez"
    )
    # Una cuenta anterior a la separación de nombres puede quedar sin apellidos.
    assert UserAccount(first_name="Carolina", last_name="").full_name == "Carolina"


@pytest.mark.parametrize(
    "password_hash, google_sub, pending",
    [(None, None, True), ("hash", None, False), (None, "sub", False), ("hash", "sub", False)],
)
def test_an_invitation_is_pending_only_without_password_and_without_google(
    password_hash, google_sub, pending
):
    user = UserAccount(password_hash=password_hash, google_sub=google_sub)

    assert user.invitation_pending is pending
    assert (user.has_password, user.google_linked) == (password_hash is not None, bool(google_sub))
