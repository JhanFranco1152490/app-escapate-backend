from fastapi.testclient import TestClient

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
