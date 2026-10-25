from datetime import date

import pytest

from app.clients import models, schemas
from app.core.security.csrf import CSRF_HEADER
from tests.factories import ClientFactory, TravelerFactory

VIEW = ["travelers.view"]
MANAGE = ["travelers.view", "travelers.manage"]

TRAVELER = {
    "first_name": "Camila",
    "last_name": "Gómez Ortiz",
    "document_type": "TI",
    "document_number": "1.098.221.334",
    "birth_date": "2012-02-03",
    "nationality": "CO",
    "notes": "Prefiere ventana.",
}

READ_ENDPOINTS = [("get", "/api/travelers"), ("get", "/api/travelers/1")]
WRITE_ENDPOINTS = [("post", "/api/travelers"), ("put", "/api/travelers/1")]


def editable(detail: dict, **changes) -> dict:
    body = {field: detail[field] for field in [*TRAVELER, "is_the_client"]}
    reference = detail["reference_client"]
    body["reference_client_id"] = reference["id"] if reference else None
    return body | {"expected_version": detail["version"]} | changes


@pytest.fixture
def frozen_today(monkeypatch):
    # La edad y la validación de la fecha usan la fecha de Bogotá.
    monkeypatch.setattr(models, "today", lambda: date(2026, 10, 25))
    monkeypatch.setattr(schemas, "today", lambda: date(2026, 10, 25))


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_a_session_every_endpoint_answers_401(csrf_client, method, path):
    assert csrf_client.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_the_permission_every_endpoint_answers_403(auth_client, method, path):
    client = auth_client(permissions=["clients.view", "clients.manage"])

    assert client.request(method, path, json={}).status_code == 403


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_viewing_is_not_enough_to_change_travelers(auth_client, method, path):
    client = auth_client(permissions=VIEW)

    assert client.request(method, path, json={}).status_code == 403


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_changes_need_the_csrf_token(auth_client, method, path):
    client = auth_client(permissions=MANAGE)
    del client.headers[CSRF_HEADER]

    assert client.request(method, path, json={}).status_code == 403


@pytest.mark.parametrize(
    "birth_date, age, is_minor",
    [
        pytest.param(date(2008, 10, 26), 17, True, id="the-day-before-turning-18"),
        pytest.param(date(2008, 10, 25), 18, False, id="the-day-of-turning-18"),
    ],
)
def test_the_list_shows_the_age_and_no_notes(auth_client, frozen_today, birth_date, age, is_minor):
    client = auth_client(permissions=VIEW)
    TravelerFactory(birth_date=birth_date, notes="Dato reservado")

    item = client.get("/api/travelers").json()["results"][0]

    assert (item["age"], item["is_minor"]) == (age, is_minor)
    assert "notes" not in item


def test_the_list_filters_by_reference_client(auth_client):
    client = auth_client(permissions=VIEW)
    marcela = ClientFactory()
    companion = TravelerFactory(reference_client=marcela)
    TravelerFactory()

    response = client.get("/api/travelers", params={"client_id": marcela.id})

    assert [item["id"] for item in response.json()["results"]] == [companion.id]
    assert response.json()["results"][0]["reference_client"]["id"] == marcela.id


def test_filtering_by_an_unknown_client_is_an_empty_page(auth_client):
    client = auth_client(permissions=VIEW)

    response = client.get("/api/travelers", params={"client_id": 999_999_999})

    assert (response.status_code, response.json()["count"]) == (200, 0)


@pytest.mark.parametrize(
    "path, status",
    [("/api/travelers/999999999", 404), ("/api/travelers/0", 422), ("/api/travelers/x", 422)],
)
def test_an_unknown_or_impossible_id(auth_client, path, status):
    client = auth_client(permissions=MANAGE)

    assert client.get(path).status_code == status
    assert client.put(path, json=TRAVELER | {"expected_version": 1}).status_code == status


def test_registering_answers_201_with_the_detail(auth_client, frozen_today):
    client = auth_client(permissions=MANAGE)
    marcela = ClientFactory(first_name="Marcela", last_name="Gómez Ortiz")

    response = client.post(
        "/api/travelers",
        json=TRAVELER | {"reference_client_id": marcela.id, "data_consent": True},
    )

    assert response.status_code == 201
    detail = response.json()
    assert detail["reference_client"] == {"id": marcela.id, "display_name": "Marcela Gómez Ortiz"}
    assert (detail["age"], detail["is_minor"], detail["notes"]) == (14, True, "Prefiere ventana.")


def test_problems_with_the_data_answer_422(auth_client):
    client = auth_client(permissions=MANAGE)

    response = client.post(
        "/api/travelers",
        json=TRAVELER | {"reference_client_id": 999_999_999, "data_consent": True},
    )

    assert response.status_code == 422
    assert response.json()["fields"] == {"reference_client_id": ["Elige un cliente registrado."]}


def test_editing_and_its_stale_version(auth_client):
    client = auth_client(permissions=MANAGE)
    created = client.post("/api/travelers", json=TRAVELER | {"data_consent": True}).json()

    edited = client.put(f"/api/travelers/{created['id']}", json=editable(created, notes="Pasillo"))
    stale = client.put(f"/api/travelers/{created['id']}", json=editable(created, notes="Ventana"))

    assert (edited.status_code, edited.json()["notes"], edited.json()["version"]) == (
        200,
        "Pasillo",
        2,
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")


def test_the_openapi_describes_the_traveler_endpoints(app):
    paths = app.openapi()["paths"]

    assert set(paths["/api/travelers"]) == {"get", "post"}
    assert set(paths["/api/travelers/{traveler_id}"]) == {"get", "put"}
    assert "Page_TravelerListItem_" in str(paths["/api/travelers"]["get"])
