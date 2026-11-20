import pytest
from sqlmodel import select

from app.accounts.models import Role


@pytest.fixture
def administrator_role(session):
    return session.exec(select(Role).where(Role.is_protected)).one()


@pytest.fixture
def advisor_role(session):
    return session.exec(select(Role).where(Role.name == "Asesor comercial")).one()


@pytest.fixture
def operations_role(session):
    return session.exec(select(Role).where(Role.name == "Operativo")).one()
