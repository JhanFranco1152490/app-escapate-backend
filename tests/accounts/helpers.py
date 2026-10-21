import time

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.factories import PASSWORD
from tests.http import attach_csrf

DOCUMENT = "1090123456"

# Los datos de una persona nueva tal como los envía el formulario de usuarios.
NEW_USER = {
    "first_name": "Laura",
    "last_name": "Rojas",
    "email": "laura.rojas@gmail.com",
    "document_type": "CC",
    "document_number": "1090123456",
    "phone": "3001234567",
}

VIEW_USERS = ["users.view"]
MANAGE_USERS = ["users.view", "users.manage"]


def login(client: TestClient, **overrides):
    body = {"document_type": "CC", "document_number": DOCUMENT, "password": PASSWORD}
    return client.post("/api/auth/login", json=body | overrides)


def set_cookies(response) -> dict[str, str]:
    """Cabeceras Set-Cookie de la respuesta, por nombre de cookie."""
    headers = [value for name, value in response.headers.multi_items() if name == "set-cookie"]
    return {header.split("=", 1)[0]: header for header in headers}


def second_client(app) -> TestClient:
    """Otro navegador: sus cookies no se mezclan con las del cliente de la prueba."""
    other = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    return attach_csrf(other)


_WAITING_ON_A_LOCK = "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"


def wait_until_blocked(engine, waiting: int) -> None:
    """Espera a que `waiting` transacciones queden detenidas esperando un bloqueo."""
    deadline = time.monotonic() + 10
    with engine.connect() as connection:
        while time.monotonic() < deadline:
            blocked = connection.execute(text(_WAITING_ON_A_LOCK)).scalar_one()
            # PostgreSQL guarda una foto de pg_stat_activity por transacción: sin cerrarla,
            # cada vuelta vería lo mismo que la primera.
            connection.rollback()
            if blocked >= waiting:
                return
            time.sleep(0.05)
    raise AssertionError("las transacciones nunca quedaron esperando el bloqueo")
