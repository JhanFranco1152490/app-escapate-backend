import pytest
from sqlalchemy import delete
from sqlmodel import col, func, select

from app import cli
from app.accounts.demo_data import DEMO_ACCOUNTS
from app.accounts.models import Role, UserAccount
from app.accounts.passwords import password_problems
from app.clients.models import Client, Traveler
from app.core.config import settings
from app.suppliers.models import Supplier
from tests.accounts.helpers import login
from tests.factories import RoleFactory, UserAccountFactory

PASSWORDS = [account.password for account in DEMO_ACCOUNTS]


@pytest.fixture
def seed_allowed(monkeypatch):
    monkeypatch.setattr(settings, "allow_demo_seed", True)


def count(session, model) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


def demo_user(session, account) -> UserAccount:
    statement = select(UserAccount).where(
        UserAccount.document_type == account.document_type,
        UserAccount.document_number == account.document_number,
    )
    return session.exec(statement).one()


def test_the_demo_passwords_meet_the_password_policy():
    for account in DEMO_ACCOUNTS:
        assert not password_problems(
            account.password, email=account.email, document_number=account.document_number
        )


def test_it_refuses_to_run_without_the_environment_flag(session, capsys):
    before = count(session, UserAccount)

    assert cli.main(["seed-demo"], session=session) == 1

    assert "ALLOW_DEMO_SEED" in capsys.readouterr().err
    assert count(session, UserAccount) == before


def test_it_creates_one_account_per_seeded_role(session, seed_allowed, capsys):
    assert cli.main(["seed-demo"], session=session) == 0

    roles = {account.role_name: demo_user(session, account).role for account in DEMO_ACCOUNTS}
    assert roles["Administrador"].is_protected
    assert {name for name, role in roles.items() if not role.is_protected} == {
        "Asesor comercial",
        "Encargado de proveedores",
        "Operativo",
    }
    assert all(role.name == name for name, role in roles.items())
    assert all(demo_user(session, account).is_active for account in DEMO_ACCOUNTS)


def test_every_demo_account_can_sign_in(session, csrf_client, seed_allowed):
    cli.main(["seed-demo"], session=session)

    for account in DEMO_ACCOUNTS:
        response = login(
            csrf_client,
            document_type=account.document_type,
            document_number=account.document_number,
            password=account.password,
        )
        assert response.status_code == 200, account.email


def test_running_it_twice_skips_the_existing_accounts(session, seed_allowed, capsys):
    cli.main(["seed-demo"], session=session)
    capsys.readouterr()
    before = count(session, UserAccount)

    assert cli.main(["seed-demo"], session=session) == 0

    assert count(session, UserAccount) == before
    output = capsys.readouterr().out
    assert output.count("omitida") == len(DEMO_ACCOUNTS)
    assert "creada" not in output.replace("omitida", "")


def test_the_output_lists_role_document_and_email_but_no_password(session, seed_allowed, capsys):
    cli.main(["seed-demo", "--with-demo-data"], session=session)
    cli.main(["seed-demo", "--with-demo-data"], session=session)

    printed = capsys.readouterr()
    output = printed.out + printed.err
    for account in DEMO_ACCOUNTS:
        assert account.email in output
        assert account.document_number in output
        assert account.role_name in output
    assert not any(password in output for password in PASSWORDS)


def test_the_administrator_role_is_found_as_protected_not_by_name(
    session, seed_allowed, administrator_role
):
    administrator_role.name = "Gerencia"
    session.flush()
    RoleFactory(name="Administrador")

    cli.main(["seed-demo"], session=session)

    admin = demo_user(session, DEMO_ACCOUNTS[0])
    assert admin.role_id == administrator_role.id


def test_a_missing_role_creates_nothing_and_names_the_role(session, seed_allowed, capsys):
    session.exec(delete(Role).where(col(Role.name) == "Operativo"))
    before = count(session, UserAccount)

    assert cli.main(["seed-demo"], session=session) == 1

    assert "Operativo" in capsys.readouterr().err
    assert count(session, UserAccount) == before


def test_an_email_used_by_another_person_fails_without_printing_a_password(
    session, seed_allowed, capsys
):
    UserAccountFactory(email=DEMO_ACCOUNTS[1].email)

    assert cli.main(["seed-demo"], session=session) == 1

    printed = capsys.readouterr()
    assert "correo" in printed.err
    assert not any(password in printed.out + printed.err for password in PASSWORDS)


def test_demo_data_is_only_loaded_when_asked(session, seed_allowed):
    cli.main(["seed-demo"], session=session)

    assert (count(session, Client), count(session, Traveler), count(session, Supplier)) == (
        0,
        0,
        0,
    )


def test_with_demo_data_loads_clients_travelers_and_suppliers_once(session, seed_allowed, capsys):
    assert cli.main(["seed-demo", "--with-demo-data"], session=session) == 0
    counts = (count(session, Client), count(session, Traveler), count(session, Supplier))
    capsys.readouterr()

    assert cli.main(["seed-demo", "--with-demo-data"], session=session) == 0

    assert min(counts) > 0
    assert (count(session, Client), count(session, Traveler), count(session, Supplier)) == counts
    assert "creado" not in capsys.readouterr().out.replace("omitido", "")


def test_the_demo_data_report_names_each_service_and_its_supplier(session, seed_allowed, capsys):
    cli.main(["seed-demo", "--with-demo-data"], session=session)

    output = capsys.readouterr().out
    assert "Registro" in output
    assert "Habitación familiar (Hotel Demostración)" in output
    assert "NIT 9000001114" in output
