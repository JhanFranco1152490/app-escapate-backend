from fastapi.testclient import TestClient

from tests.factories import PASSWORD

DOCUMENT = "1090123456"


def login(client: TestClient, **overrides):
    body = {"document_type": "CC", "document_number": DOCUMENT, "password": PASSWORD}
    return client.post("/api/auth/login", json=body | overrides)


def set_cookies(response) -> dict[str, str]:
    """Cabeceras Set-Cookie de la respuesta, por nombre de cookie."""
    headers = [value for name, value in response.headers.multi_items() if name == "set-cookie"]
    return {header.split("=", 1)[0]: header for header in headers}
