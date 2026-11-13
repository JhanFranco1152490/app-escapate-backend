from datetime import date, timedelta

import pytest

from app.core.security.csrf import CSRF_HEADER
from app.suppliers import tourist_service_models
from app.suppliers.services import tourist_service_queries
from tests.factories import ServiceRateFactory, SupplierFactory, TouristServiceFactory

VIEW = ["suppliers.view", "tourist_services.view"]
MANAGE = VIEW + ["tourist_services.manage"]
TODAY = date(2026, 11, 7)

LODGING = {
    "service_type": "lodging",
    "name": "Habitación familiar conectada",
    "destination": "Cartagena",
    "description": "Dos habitaciones conectadas.",
    "conditions": "Cancelación sin costo hasta 30 días antes.",
    "attributes": {
        "lodging_kind": "hotel",
        "stars": 4,
        "meal_plan": "breakfast",
        "max_capacity": 4,
        "check_in_time": "15:00",
        "includes": ["wifi"],
    },
}

READ_ENDPOINTS = [
    ("get", "/api/suppliers/1/tourist-services"),
    ("get", "/api/tourist-services/1"),
]
WRITE_ENDPOINTS = [
    ("post", "/api/suppliers/1/tourist-services"),
    ("put", "/api/tourist-services/1"),
    ("post", "/api/tourist-services/1/deactivate"),
    ("post", "/api/tourist-services/1/activate"),
]


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    for module in (tourist_service_queries, tourist_service_models):
        monkeypatch.setattr(module, "today", lambda: TODAY)


def register(client, supplier, **changes) -> dict:
    response = client.post(
        f"/api/suppliers/{supplier.id}/tourist-services", json=LODGING | changes
    )
    assert response.status_code == 201, response.json()
    return response.json()


def editable(detail: dict, **changes) -> dict:
    """El cuerpo del PUT a partir de la ficha, como lo arma el formulario de edición."""
    body = {field: detail[field] for field in LODGING if field != "attributes"}
    attributes = {key: value for key, value in detail["attributes"].items() if value is not None}
    return body | {"attributes": attributes, "expected_version": detail["version"]} | changes


# --- Acceso --------------------------------------------------------------------------------


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_a_session_every_endpoint_answers_401(csrf_client, method, path):
    assert csrf_client.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_the_permission_every_endpoint_answers_403(auth_client, method, path):
    client = auth_client(permissions=["suppliers.view", "suppliers.manage"])

    response = client.request(method, path, json={})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_viewing_is_not_enough_to_change_services(auth_client, method, path):
    response = auth_client(permissions=VIEW).request(method, path, json={})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_changes_need_the_csrf_token(auth_client, method, path):
    client = auth_client(permissions=MANAGE)
    del client.headers[CSRF_HEADER]

    assert client.request(method, path, json={}).status_code == 403


# --- Lectura -------------------------------------------------------------------------------


def test_the_list_of_a_supplier_answers_a_page_with_the_current_rates(auth_client):
    client = auth_client(permissions=VIEW)
    service = TouristServiceFactory(name="Habitación doble")
    ServiceRateFactory(tourist_service=service, valid_from=TODAY)
    ServiceRateFactory(tourist_service=service, valid_from=TODAY + timedelta(days=1))

    response = client.get(f"/api/suppliers/{service.supplier_id}/tourist-services")

    assert response.status_code == 200
    assert response.json()["results"] == [
        {
            "id": service.id,
            "service_type": "lodging",
            "name": "Habitación doble",
            "destination": "Cartagena",
            "is_active": True,
            "current_rate_count": 1,
        }
    ]


def test_the_detail_answers_the_attributes_of_its_type(auth_client):
    client = auth_client(permissions=MANAGE)
    created = register(client, SupplierFactory())

    response = client.get(f"/api/tourist-services/{created['id']}")

    body = response.json()
    assert response.status_code == 200
    assert body["attributes"] == {
        "lodging_kind": "hotel",
        "stars": 4,
        "meal_plan": "breakfast",
        "max_capacity": 4,
        "check_in_time": "15:00",
        "check_out_time": None,
        "includes": ["wifi"],
    }
    assert (body["description"], body["conditions"]) == (
        LODGING["description"],
        LODGING["conditions"],
    )
    assert set(body) >= {"supplier", "created_by", "deactivated_by", "version"}


def test_the_supplier_list_counts_its_active_services(auth_client):
    client = auth_client(permissions=VIEW)
    supplier = SupplierFactory(trade_name="Hotel Caribe Azul")
    TouristServiceFactory(supplier=supplier)
    TouristServiceFactory(supplier=supplier, inactive=True)

    results = client.get("/api/suppliers", params={"q": "caribe"}).json()["results"]

    assert [item["active_service_count"] for item in results] == [1]


@pytest.mark.parametrize(
    "path, status",
    [
        ("/api/tourist-services/999999999", 404),
        ("/api/suppliers/999999999/tourist-services", 404),
        ("/api/tourist-services/0", 422),
        ("/api/tourist-services/abc", 422),
    ],
)
def test_an_unknown_or_impossible_id(auth_client, path, status):
    assert auth_client(permissions=VIEW).get(path).status_code == status


# --- Escritura -----------------------------------------------------------------------------


def test_registering_answers_201_with_the_detail(auth_client):
    client = auth_client(permissions=MANAGE)
    supplier = SupplierFactory()

    created = register(client, supplier)

    assert created["supplier"] == {
        "id": supplier.id,
        "trade_name": supplier.trade_name,
        "is_active": True,
    }
    assert (created["version"], created["current_rate_count"]) == (1, 0)


def test_missing_attributes_answer_422_with_their_path(auth_client):
    client = auth_client(permissions=MANAGE)
    supplier = SupplierFactory()

    response = client.post(
        f"/api/suppliers/{supplier.id}/tourist-services",
        json=LODGING | {"name": "", "attributes": {"lodging_kind": "hotel"}},
    )

    assert response.status_code == 422
    assert set(response.json()["fields"]) == {"name", "attributes.max_capacity"}


def test_a_type_the_supplier_does_not_offer_answers_422(auth_client):
    client = auth_client(permissions=MANAGE)
    supplier = SupplierFactory(categories=["tours"])

    response = client.post(f"/api/suppliers/{supplier.id}/tourist-services", json=LODGING)

    assert response.status_code == 422
    assert list(response.json()["fields"]) == ["service_type"]


def test_an_inactive_supplier_answers_409(auth_client):
    client = auth_client(permissions=MANAGE)
    supplier = SupplierFactory(inactive=True)

    response = client.post(f"/api/suppliers/{supplier.id}/tourist-services", json=LODGING)

    assert (response.status_code, response.json()["code"]) == (409, "supplier_inactive")


def test_editing_answers_the_saved_detail(auth_client):
    client = auth_client(permissions=MANAGE)
    created = register(client, SupplierFactory())

    response = client.put(
        f"/api/tourist-services/{created['id']}", json=editable(created, destination="San Andrés")
    )

    assert response.status_code == 200
    assert (response.json()["destination"], response.json()["version"]) == ("San Andrés", 2)


def test_editing_over_an_old_version_answers_409(auth_client):
    client = auth_client(permissions=MANAGE)
    created = register(client, SupplierFactory())

    response = client.put(
        f"/api/tourist-services/{created['id']}", json=editable(created, expected_version=9)
    )

    assert (response.status_code, response.json()["code"]) == (409, "stale_version")


@pytest.mark.parametrize("extra", [{"supplier_id": 1}, {"is_active": False}, {"created_by_id": 1}])
def test_editing_rejects_what_is_not_editable(auth_client, extra):
    client = auth_client(permissions=MANAGE)
    created = register(client, SupplierFactory())

    response = client.put(
        f"/api/tourist-services/{created['id']}", json=editable(created, **extra)
    )

    assert response.status_code == 422
    assert list(response.json()["fields"]) == list(extra)


def test_deactivating_and_activating(auth_client):
    client = auth_client(permissions=MANAGE)
    created = register(client, SupplierFactory())
    path = f"/api/tourist-services/{created['id']}"

    off = client.post(f"{path}/deactivate", json={"expected_version": 1})
    on = client.post(f"{path}/activate", json={"expected_version": 2})

    assert (off.status_code, off.json()["is_active"]) == (200, False)
    assert off.json()["deactivated_by"] is not None
    assert (on.status_code, on.json()["is_active"], on.json()["deactivated_at"]) == (
        200,
        True,
        None,
    )


def test_activating_with_an_inactive_supplier_answers_409(auth_client):
    client = auth_client(permissions=MANAGE)
    service = TouristServiceFactory(supplier=SupplierFactory(inactive=True), inactive=True)

    response = client.post(
        f"/api/tourist-services/{service.id}/activate", json={"expected_version": service.version}
    )

    assert (response.status_code, response.json()["code"]) == (409, "supplier_inactive")


def test_the_openapi_describes_the_service_endpoints(app):
    schema = app.openapi()
    paths = schema["paths"]

    assert set(paths["/api/suppliers/{supplier_id}/tourist-services"]) == {"get", "post"}
    assert set(paths["/api/tourist-services/{service_id}"]) == {"get", "put"}
    assert set(paths["/api/tourist-services/{service_id}/deactivate"]) == {"post"}
    assert set(paths["/api/tourist-services/{service_id}/activate"]) == {"post"}
    attributes = schema["components"]["schemas"]["TouristServiceDetail"]["properties"][
        "attributes"
    ]
    assert len(attributes["anyOf"]) == 8
