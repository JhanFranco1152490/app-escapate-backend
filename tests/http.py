from fastapi.testclient import TestClient

from app.core.security.csrf import CSRF_HEADER


def attach_csrf(client: TestClient) -> TestClient:
    """Pide el token CSRF y lo deja en las cabeceras, como hace el frontend."""
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    client.headers[CSRF_HEADER] = token
    return client
