import pytest
from sqlmodel import func, select

from app import cli
from app.accounts.models import UserAccount
from app.accounts.services.admin_setup import ADMIN_ROLE, SetupError, create_admin
from app.core.security.passwords import verify_password
from tests.factories import UserAccountFactory

DATA = {
    "full_name": "Dueño de la Agencia",
    "email": " Dueno@Example.com ",
    "document_type": "CC",
    "document_number": "1.090.000.001",
    "password": "una contrasena larga",
}


def count_accounts(session) -> int:
    return session.exec(select(func.count()).select_from(UserAccount)).one()


def test_creates_an_active_administrator_with_normalized_data(session):
    user = create_admin(session, **DATA)

    assert user.role.name == ADMIN_ROLE
    assert (user.email, user.document_number, user.is_active) == (
        "dueno@example.com",
        "1090000001",
        True,
    )
    assert verify_password(DATA["password"], user.password_hash)[0]


@pytest.mark.parametrize(
    "field, value",
    [
        ("email", "dueno@example.com"),
        ("document_number", "1090000001"),
    ],
)
def test_duplicates_fail_without_creating_anything(session, field, value):
    UserAccountFactory(**{field: value})
    before = count_accounts(session)

    with pytest.raises(SetupError):
        create_admin(session, **DATA)

    assert count_accounts(session) == before


@pytest.mark.parametrize(
    "field, value",
    [
        ("full_name", "   "),
        ("email", "sin-arroba"),
        ("document_type", "NIT"),
        ("document_number", "12"),
        ("password", "corta"),
        ("password", "dueno@example.com"),
    ],
)
def test_invalid_data_is_rejected_with_a_message(session, field, value):
    with pytest.raises(SetupError) as error:
        create_admin(session, **DATA | {field: value})

    assert error.value.messages


def answers(*values):
    iterator = iter(values)
    return lambda prompt="": next(iterator)


def test_cli_asks_for_the_data_and_creates_the_account(session, monkeypatch, capsys):
    monkeypatch.setattr(
        "builtins.input", answers("Dueño", "dueno@example.com", "CC", "1090000001")
    )
    monkeypatch.setattr(cli.getpass, "getpass", answers(DATA["password"], DATA["password"]))

    exit_code = cli.main(["create-admin"], session=session)

    assert exit_code == 0
    assert "Administrador creado" in capsys.readouterr().out
    assert session.exec(select(UserAccount).where(UserAccount.email == "dueno@example.com")).one()


def test_cli_rejects_a_different_confirmation(session, monkeypatch, capsys):
    monkeypatch.setattr(
        "builtins.input", answers("Dueño", "dueno@example.com", "CC", "1090000001")
    )
    monkeypatch.setattr(cli.getpass, "getpass", answers(DATA["password"], "otra cosa distinta"))
    before = count_accounts(session)

    assert cli.main(["create-admin"], session=session) == 1
    assert "no coinciden" in capsys.readouterr().err
    assert count_accounts(session) == before
