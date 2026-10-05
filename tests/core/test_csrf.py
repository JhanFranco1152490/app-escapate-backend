import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import create_app

router = APIRouter()


@router.post("/api/test/things")
def create_thing():
    return {"ok": True}


@router.get("/api/test/things")
def list_things():
    return []


@router.post("/health-like")
def outside_api():
    return {"ok": True}


@pytest.fixture
def client(app, client):
    app.include_router(router)
    return client


def get_token(client) -> str:
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def set_cookie_header(response) -> str:
    return response.headers["set-cookie"]


def test_csrf_endpoint_sets_an_http_only_cookie_under_api(client):
    response = client.get("/api/auth/csrf")

    cookie = set_cookie_header(response)
    assert cookie.startswith("escapate_csrf=")
    assert "HttpOnly" in cookie
    assert "Path=/api/" in cookie
    assert response.json()["csrf_token"] in cookie


@pytest.mark.parametrize("secure", [True, False])
def test_cookie_secure_flag_follows_settings(client, monkeypatch, secure):
    monkeypatch.setattr(settings, "cookie_secure", secure)

    cookie = set_cookie_header(client.get("/api/auth/csrf"))

    assert ("Secure" in cookie) is secure


def test_mutation_with_matching_token_passes(client):
    token = get_token(client)

    response = client.post("/api/test/things", headers={"X-CSRF-Token": token})

    assert response.status_code == 200


def test_mutation_without_header_is_denied(client):
    get_token(client)

    response = client.post("/api/test/things")

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_mutation_with_a_different_header_is_denied(client):
    get_token(client)

    response = client.post("/api/test/things", headers={"X-CSRF-Token": "other"})

    assert response.status_code == 403


def test_mutation_without_cookie_is_denied(client):
    token = get_token(client)
    client.cookies.clear()

    response = client.post("/api/test/things", headers={"X-CSRF-Token": token})

    assert response.status_code == 403


@pytest.mark.parametrize("method", ["get", "head", "options"])
def test_safe_methods_do_not_need_a_token(client, method):
    assert getattr(client, method)("/api/test/things").status_code != 403


def test_routes_outside_api_do_not_need_a_token(client):
    assert client.post("/health-like").status_code == 200


def build_cors_client() -> TestClient:
    app = create_app(Settings(secret_key="x" * 32, frontend_origin="https://app.example.com"))
    return TestClient(app, base_url="https://testserver")


def preflight(client: TestClient, origin: str):
    return client.options(
        "/api/auth/csrf",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )


def test_cors_allows_the_frontend_with_credentials():
    response = preflight(build_cors_client(), "https://app.example.com")

    assert response.headers["access-control-allow-origin"] == "https://app.example.com"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "x-csrf-token" in response.headers["access-control-allow-headers"].lower()


def test_cors_rejects_other_origins():
    response = preflight(build_cors_client(), "https://evil.example.com")

    assert "access-control-allow-origin" not in response.headers
