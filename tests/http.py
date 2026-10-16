from fastapi import Request
from fastapi.testclient import TestClient

from app.core.security.csrf import CSRF_HEADER


def attach_csrf(client: TestClient) -> TestClient:
    """Pide el token CSRF y lo deja en las cabeceras, como hace el frontend."""
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    client.headers[CSRF_HEADER] = token
    return client


def fake_request(path: str = "/api/test", query: str = "") -> Request:
    """Un `Request` mínimo para llamar a servicios que arman los enlaces de paginación."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": path,
            "query_string": query.encode(),
            "headers": [],
        }
    )
