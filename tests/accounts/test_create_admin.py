import pytest
from sqlalchemy import delete
from sqlmodel import col, func, select

from app import cli
from app.accounts.models import Role, UserAccount
from app.accounts.services.account_setup import SetupError
from app.accounts.services.admin_setup import create_admin
from app.core.security.passwords import verify_password
from tests.factories import RoleFactory, UserAccountFactory

DATA = {
    "first_name": "Dueño",
    "last_name": "de la Agencia",
    "email": " Dueno@Example.com ",
    "document_type": "CC",
    "document_number": "1.090.000.001",
    "phone": "300 123 4567",
    "password": "una contrasena larga",
}


def count_accounts(session) -> int:
    return session.exec(select(func.count()).select_from(UserAccount)).one()


def test_creates_an_active_administrator_with_normalized_data(session):
    user = create_admin(session, **DATA)

    assert user.role.is_protected
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
        ("phone", "3001234567"),
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
        ("first_name", "   "),
        ("last_name", "   "),
        ("email", "sin-arroba"),
        ("document_type", "NIT"),
        ("document_number", "12"),
        ("phone", "123"),
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
        "builtins.input",
        answers("Dueño", "de la Agencia", "dueno@example.com", "CC", "1090000001", "3001234567"),
    )
    monkeypatch.setattr(cli.getpass, "getpass", answers(DATA["password"], DATA["password"]))

    exit_code = cli.main(["create-admin"], session=session)

    assert exit_code == 0
    assert "Administrador creado" in capsys.readouterr().out
    assert session.exec(select(UserAccount).where(UserAccount.email == "dueno@example.com")).one()


def test_cli_rejects_a_different_confirmation(session, monkeypatch, capsys):
    monkeypatch.setattr(
        "builtins.input",
        answers("Dueño", "de la Agencia", "dueno@example.com", "CC", "1090000001", "3001234567"),
    )
    monkeypatch.setattr(cli.getpass, "getpass", answers(DATA["password"], "otra cosa distinta"))
    before = count_accounts(session)

    assert cli.main(["create-admin"], session=session) == 1
    assert "no coinciden" in capsys.readouterr().err
    assert count_accounts(session) == before


def test_cli_reports_each_invalid_field_with_its_name_and_fails(session, monkeypatch, capsys):
    monkeypatch.setattr(
        "builtins.input",
        answers("Dueño", "de la Agencia", "dueno@example.com", "CC", "1090000001", "123"),
    )
    monkeypatch.setattr(cli.getpass, "getpass", answers(DATA["password"], DATA["password"]))
    before = count_accounts(session)

    assert cli.main(["create-admin"], session=session) == 1
    assert "Celular: Debe ser un celular colombiano de 10 dígitos." in capsys.readouterr().err
    assert count_accounts(session) == before


def test_the_administrator_role_is_found_as_protected_not_by_name(session, administrator_role):
    administrator_role.name = "Gerencia"
    session.flush()
    RoleFactory(name="Administrador")

    user = create_admin(session, **DATA)

    assert user.role_id == administrator_role.id


def test_a_missing_administrator_role_asks_to_apply_the_migrations(session):
    session.exec(delete(Role).where(col(Role.is_protected)))

    with pytest.raises(SetupError) as error:
        create_admin(session, **DATA)

    assert "migraciones" in error.value.messages[0]
