import pytest
from sqlmodel import select

from app.accounts.models import Role
from app.accounts.services import password_reset
from app.common.email import EmailDeliveryError

# Una dirección dentro del mensaje del error: las pruebas comprueban que no llegue a los logs.
LEAKY_PROVIDER_MESSAGE = "el proveedor rechazó a secreto@example.com"


@pytest.fixture
def sent(monkeypatch):
    """Los correos que la aplicación intentó enviar, como los argumentos de `send_email`."""
    calls = []
    monkeypatch.setattr(password_reset, "send_email", lambda **kwargs: calls.append(kwargs))
    return calls


@pytest.fixture
def email_down(monkeypatch):
    """El proveedor de correo falla en cada envío."""

    def failing(**kwargs):
        raise EmailDeliveryError(LEAKY_PROVIDER_MESSAGE)

    monkeypatch.setattr(password_reset, "send_email", failing)


@pytest.fixture
def administrator_role(session):
    return session.exec(select(Role).where(Role.is_protected)).one()


@pytest.fixture
def advisor_role(session):
    return session.exec(select(Role).where(Role.name == "Asesor comercial")).one()
