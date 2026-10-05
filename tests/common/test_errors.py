import logging

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm.exc import StaleDataError

from app.common.errors import ApiError
from app.core.config import Settings
from app.main import create_app

SECRET = "x" * 32


class Conflict(ApiError):
    status_code, code, detail = 409, "duplicate_thing", "Ya existe."


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


router = APIRouter(prefix="/api/test")


@router.get("/api-error")
def raise_api_error():
    raise Conflict(fields={"name": ["Ya está en uso."]})


@router.post("/items")
def create_item(item: ItemIn):
    return item


@router.get("/items")
def list_items():
    return []


@router.get("/stale")
def raise_stale():
    raise StaleDataError("version mismatch")


@router.get("/boom")
def raise_unhandled():
    email = "ana@" + "example.com"
    raise RuntimeError(email)


def build_client(debug: bool = False) -> TestClient:
    app = create_app(Settings(secret_key=SECRET, debug=debug))
    app.include_router(router)
    return TestClient(app, base_url="https://testserver", raise_server_exceptions=False)


@pytest.fixture
def client():
    return build_client()


def test_api_error_keeps_status_code_and_fields(client):
    response = client.get("/api/test/api-error")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Ya existe.",
        "code": "duplicate_thing",
        "fields": {"name": ["Ya está en uso."]},
    }


def test_undeclared_field_is_a_validation_error_naming_the_field(client):
    response = client.post("/api/test/items", json={"name": "a", "price": 1})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert "price" in body["fields"]


def test_missing_field_is_reported_by_name(client):
    response = client.post("/api/test/items", json={})

    assert response.status_code == 422
    assert list(response.json()["fields"]) == ["name"]


def test_unknown_route_is_not_found(client):
    response = client.get("/api/nothing-here")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert response.json()["fields"] == {}


def test_unsupported_method_is_method_not_allowed(client):
    response = client.delete("/api/test/items")

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


def test_stale_data_is_a_stale_version_conflict(client):
    response = client.get("/api/test/stale")

    assert response.status_code == 409
    assert response.json()["code"] == "stale_version"


def test_unhandled_error_hides_the_message(client, caplog):
    with caplog.at_level(logging.ERROR):
        response = client.get("/api/test/boom")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "example.com" not in response.text
    assert "RuntimeError" in caplog.text
    assert "example.com" not in caplog.text


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/test/items"),
        ("get", "/api/nothing-here"),
        ("post", "/api/test/items"),
        ("get", "/api/test/boom"),
    ],
)
def test_api_responses_are_not_stored(client, method, path):
    response = getattr(client, method)(path)

    assert response.headers["cache-control"] == "no-store"


def test_health_may_be_cached(client):
    assert "cache-control" not in client.get("/health").headers


def test_schema_is_hidden_outside_debug(client):
    assert client.get("/api/openapi.json").status_code == 404
    assert client.get("/api/docs").status_code == 404


def test_schema_documents_errors_with_the_common_shape():
    client = build_client(debug=True)

    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    assert "ErrorResponse" in schema["components"]["schemas"]
    error = schema["paths"]["/api/test/items"]["post"]["responses"]["422"]
    assert error["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert client.get("/api/docs").status_code == 200
