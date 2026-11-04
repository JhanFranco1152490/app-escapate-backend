"""Carga de las cuentas de demostración: una por rol sembrado. Repetible: una cuenta con un
documento ya registrado se omite."""

from dataclasses import dataclass

from sqlmodel import Session, select

from app.accounts.demo_data import DEMO_ACCOUNTS, DemoAccount
from app.accounts.models import Role, UserAccount
from app.accounts.services.account_setup import create_account, missing_role
from app.accounts.services.admin_setup import find_administrator_role
from app.accounts.services.password_login import find_by_document


@dataclass(frozen=True)
class SeededAccount:
    user: UserAccount
    created: bool


def _find_role(session: Session, account: DemoAccount) -> Role:
    if account.protected_role:
        return find_administrator_role(session)
    role = session.exec(select(Role).where(Role.name == account.role_name)).first()
    if role is None:
        raise missing_role(account.role_name)
    return role


def seed_demo_accounts(session: Session) -> list[SeededAccount]:
    # Todos los roles antes de crear nada: si falta uno no queda una carga a medias.
    roles = [_find_role(session, account) for account in DEMO_ACCOUNTS]

    seeded = []
    for account, role in zip(DEMO_ACCOUNTS, roles, strict=True):
        existing = find_by_document(session, account.document_type, account.document_number)
        if existing is not None:
            seeded.append(SeededAccount(existing, created=False))
            continue
        user = create_account(
            session,
            role,
            first_name=account.first_name,
            last_name=account.last_name,
            email=account.email,
            document_type=account.document_type,
            document_number=account.document_number,
            phone=account.phone,
            password=account.password,
        )
        seeded.append(SeededAccount(user, created=True))
    return seeded
