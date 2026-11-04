"""Creación de un administrador desde la terminal: la primera cuenta, o un respaldo si el único
administrador pierde el acceso."""

from sqlmodel import Session, select

from app.accounts.models import Role, UserAccount
from app.accounts.services.account_setup import create_account, missing_role


def find_administrator_role(session: Session) -> Role:
    # Por is_protected y no por nombre: el nombre se puede editar y otro rol podría tomarlo.
    role = session.exec(select(Role).where(Role.is_protected)).first()
    if role is None:
        raise missing_role("Administrador")
    return role


def create_admin(
    session: Session,
    *,
    first_name: str,
    last_name: str,
    email: str,
    document_type: str,
    document_number: str,
    phone: str,
    password: str,
) -> UserAccount:
    return create_account(
        session,
        find_administrator_role(session),
        first_name=first_name,
        last_name=last_name,
        email=email,
        document_type=document_type,
        document_number=document_number,
        phone=phone,
        password=password,
    )
