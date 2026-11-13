import logging
from datetime import date

import pytest

from app.core.security.csrf import CSRF_HEADER
from app.suppliers import tourist_service_models
from app.suppliers.services import rate_queries
from tests.factories import ServiceRateFactory, TouristServiceFactory

VIEW = ["suppliers.view", "tourist_services.view"]
MANAGE = VIEW + ["tourist_services.manage"]
TODAY = date(2026, 11, 7)

RATE = {
    "name": "Temporada alta",
    "valid_from": "2026-12-15",
    "valid_until": "2027-01-15",
    "currency": "COP",
    "charge_unit": "per_night",
    "amount": "710000",
    "conditions": "Hasta 4 personas. Mínimo 5 noches.",
}

READ_ENDPOINTS = [("get", "/api/tourist-services/1/rates")]
WRITE_ENDPOINTS = [
    ("post", "/api/tourist-services/1/rates"),
    ("put", "/api/tourist-services/1/rates/1"),
    ("delete", "/api/tourist-services/1/rates/1?expected_version=1"),
]


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    for module in (rate_queries, tourist_service_models):
        monkeypatch.setattr(module, "today", lambda: TODAY)


def _path(service, rate=None) -> str:
    base = f"/api/tourist-services/{service.id}/rates"
    return base if rate is None else f"{base}/{rate['id']}"


def register(client, service, **changes) -> dict:
    response = client.post(_path(service), json=RATE | changes)
    assert response.status_code == 201, response.json()
    return response.json()


# --- Acceso --------------------------------------------------------------------------------


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_a_session_every_endpoint_answers_401(csrf_client, method, path):
    assert csrf_client.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_the_permission_every_endpoint_answers_403(auth_client, method, path):
    response = auth_client(permissions=["suppliers.view"]).request(method, path, json={})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_viewing_is_not_enough_to_change_rates(auth_client, method, path):
    response = auth_client(permissions=VIEW).request(method, path, json={})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_changes_need_the_csrf_token(auth_client, method, path):
    client = auth_client(permissions=MANAGE)
    del client.headers[CSRF_HEADER]

    assert client.request(method, path, json={}).status_code == 403


# --- Lectura y escritura -------------------------------------------------------------------


def test_registering_answers_201_with_the_rate(auth_client):
    client = auth_client(permissions=MANAGE)

    created = register(client, TouristServiceFactory())

    assert {key: created[key] for key in RATE} == RATE
    assert (created["validity_status"], created["version"]) == ("upcoming", 1)
    assert created["created_by"] is not None


def test_the_amount_is_written_with_the_decimals_of_its_currency(auth_client):
    client = auth_client(permissions=MANAGE)
    service = TouristServiceFactory()

    pesos = register(client, service, amount="710000.00")
    dollars = register(client, service, currency="USD", amount="1250.5")

    assert (pesos["amount"], dollars["amount"]) == ("710000", "1250.50")


def test_the_list_answers_the_rates_in_order_with_their_status(auth_client):
    client = auth_client(permissions=VIEW)
    service = TouristServiceFactory()
    ServiceRateFactory(tourist_service=service, name="Próxima", valid_from=date(2026, 12, 1))
    ServiceRateFactory(tourist_service=service, name="Vigente", valid_from=date(2026, 11, 1))

    page = client.get(_path(service)).json()

    assert [(rate["name"], rate["validity_status"]) for rate in page["results"]] == [
        ("Vigente", "current"),
        ("Próxima", "upcoming"),
    ]


def test_missing_data_answers_422_with_each_field(auth_client):
    client = auth_client(permissions=MANAGE)

    response = client.post(_path(TouristServiceFactory()), json={"conditions": "Sin valor."})

    assert response.status_code == 422
    assert set(response.json()["fields"]) == {
        "name",
        "valid_from",
        "currency",
        "charge_unit",
        "amount",
    }


def test_cents_in_pesos_answer_422_on_the_amount(auth_client):
    client = auth_client(permissions=MANAGE)

    response = client.post(_path(TouristServiceFactory()), json=RATE | {"amount": "710000.5"})

    assert response.json()["fields"] == {"amount": ["En pesos el valor va sin decimales."]}


def test_a_charge_unit_of_another_type_answers_422(auth_client):
    client = auth_client(permissions=MANAGE)

    response = client.post(
        _path(TouristServiceFactory()), json=RATE | {"charge_unit": "per_cabin"}
    )

    assert (response.status_code, list(response.json()["fields"])) == (422, ["charge_unit"])


def test_an_inactive_service_answers_409(auth_client):
    client = auth_client(permissions=MANAGE)

    response = client.post(_path(TouristServiceFactory(inactive=True)), json=RATE)

    assert (response.status_code, response.json()["code"]) == (409, "service_inactive")


def test_editing_answers_the_saved_rate(auth_client):
    client = auth_client(permissions=MANAGE)
    service = TouristServiceFactory()
    created = register(client, service)

    response = client.put(
        _path(service, created), json=RATE | {"amount": "760000", "expected_version": 1}
    )

    assert response.status_code == 200
    assert (response.json()["amount"], response.json()["version"]) == ("760000", 2)


def test_editing_over_an_old_version_answers_409(auth_client):
    client = auth_client(permissions=MANAGE)
    service = TouristServiceFactory()
    created = register(client, service)

    response = client.put(_path(service, created), json=RATE | {"expected_version": 9})

    assert (response.status_code, response.json()["code"]) == (409, "stale_version")


def test_deleting_answers_204_and_the_rate_is_gone(auth_client):
    client = auth_client(permissions=MANAGE)
    service = TouristServiceFactory()
    created = register(client, service)

    response = client.delete(_path(service, created), params={"expected_version": 1})

    assert (response.status_code, response.content) == (204, b"")
    assert client.get(_path(service)).json()["count"] == 0


def test_deleting_over_an_old_version_answers_409(auth_client):
    client = auth_client(permissions=MANAGE)
    service = TouristServiceFactory()
    created = register(client, service)

    response = client.delete(_path(service, created), params={"expected_version": 9})

    assert (response.status_code, response.json()["code"]) == (409, "stale_version")


def test_deleting_without_the_version_answers_422(auth_client):
    client = auth_client(permissions=MANAGE)
    service = TouristServiceFactory()
    created = register(client, service)

    response = client.delete(_path(service, created))

    assert (response.status_code, list(response.json()["fields"])) == (422, ["expected_version"])


@pytest.mark.parametrize("method", ["put", "delete"])
def test_a_rate_of_another_service_answers_404(auth_client, method):
    client = auth_client(permissions=MANAGE)
    created = register(client, TouristServiceFactory())
    other = TouristServiceFactory()

    response = client.request(
        method,
        _path(other, created),
        params={"expected_version": 1},
        json=RATE | {"expected_version": 1},
    )

    assert response.status_code == 404


def test_an_unknown_service_answers_404(auth_client):
    client = auth_client(permissions=MANAGE)
    path = "/api/tourist-services/999999999/rates"

    assert client.get(path).status_code == 404
    assert client.post(path, json=RATE).status_code == 404


@pytest.mark.parametrize("method", ["put", "delete"])
def test_an_unknown_rate_answers_404(auth_client, method):
    client = auth_client(permissions=MANAGE)
    path = f"/api/tourist-services/{TouristServiceFactory().id}/rates/999999999"

    response = client.request(
        method, path, params={"expected_version": 1}, json=RATE | {"expected_version": 1}
    )

    assert response.status_code == 404


def test_a_rejected_rate_is_not_logged(auth_client, caplog):
    client = auth_client(permissions=MANAGE)
    caplog.set_level(logging.DEBUG)

    client.post(_path(TouristServiceFactory()), json=RATE | {"amount": "-1"})

    assert "Mínimo 5 noches" not in caplog.text


def test_the_openapi_describes_the_rate_endpoints(app):
    schema = app.openapi()
    paths = schema["paths"]

    assert set(paths["/api/tourist-services/{service_id}/rates"]) == {"get", "post"}
    assert set(paths["/api/tourist-services/{service_id}/rates/{rate_id}"]) == {"put", "delete"}
    amount = schema["components"]["schemas"]["ServiceRate"]["properties"]["amount"]
    assert amount["type"] == "string"
