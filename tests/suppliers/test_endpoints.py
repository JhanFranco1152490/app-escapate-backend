import logging
from datetime import date

import pytest

from app.core.security.csrf import CSRF_HEADER
from app.suppliers import models
from tests.factories import SupplierFactory

VIEW = ["suppliers.view"]
MANAGE = ["suppliers.view", "suppliers.manage"]

HOTEL = {
    "trade_name": "Hotel Caribe Azul",
    "legal_name": "Inversiones Caribe Azul SAS",
    "document_type": "NIT",
    "document_number": "800.197.268-4",
    "categories": ["tours", "lodging"],
    "city": "Cartagena",
    "coverage_zone": "Caribe colombiano",
    "contact_name": "Andrea Pérez",
    "contact_role": "Reservas",
    "contact_phone": "300 111 2233",
    "contact_email": "reservas@example.com",
    "payment_terms": "50 % al reservar, saldo 15 días antes",
    "commission_rate": "10",
    "agreement_valid_until": "2027-06-30",
    "notes": "Atiende de lunes a sábado.",
}

READ_ENDPOINTS = [("get", "/api/suppliers"), ("get", "/api/suppliers/1")]
WRITE_ENDPOINTS = [
    ("post", "/api/suppliers"),
    ("put", "/api/suppliers/1"),
    ("post", "/api/suppliers/1/deactivate"),
    ("post", "/api/suppliers/1/activate"),
]


def editable(detail: dict, **changes) -> dict:
    """El cuerpo del PUT a partir de la ficha, como lo arma el formulario de edición."""
    body = {field: detail[field] for field in HOTEL}
    return body | {"expected_version": detail["version"]} | changes


def register(client, **changes) -> dict:
    response = client.post("/api/suppliers", json=HOTEL | changes)
    assert response.status_code == 201
    return response.json()


# --- Acceso --------------------------------------------------------------------------------


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_a_session_every_endpoint_answers_401(csrf_client, method, path):
    assert csrf_client.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_the_permission_every_endpoint_answers_403(auth_client, method, path):
    client = auth_client(permissions=["clients.view"])

    response = client.request(method, path, json={})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_viewing_is_not_enough_to_change_suppliers(auth_client, method, path):
    client = auth_client(permissions=VIEW)

    response = client.request(method, path, json={})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_changes_need_the_csrf_token(auth_client, method, path):
    client = auth_client(permissions=MANAGE)
    del client.headers[CSRF_HEADER]

    assert client.request(method, path, json={}).status_code == 403


# --- Lectura -------------------------------------------------------------------------------


def test_the_list_answers_a_page_without_the_commercial_details(auth_client):
    client = auth_client(permissions=VIEW)
    SupplierFactory(trade_name="Hotel Caribe Azul", notes="Dato reservado")

    response = client.get("/api/suppliers", params={"q": "caribe"})

    assert response.status_code == 200
    page = response.json()
    assert page["count"] == 1
    assert set(page["results"][0]) == {
        "id",
        "trade_name",
        "legal_name",
        "document_type",
        "document_number",
        "categories",
        "city",
        "contact_name",
        "contact_email",
        "contact_phone",
        "is_active",
    }


def test_the_list_filters_by_category_and_status(auth_client):
    client = auth_client(permissions=VIEW)
    SupplierFactory(trade_name="Hotel", categories=["lodging"])
    SupplierFactory(trade_name="Naviera", categories=["cruise"], inactive=True)

    def names(**params) -> list[str]:
        results = client.get("/api/suppliers", params=params).json()["results"]
        return [item["trade_name"] for item in results]

    assert names() == ["Hotel"]
    assert names(status="inactive") == ["Naviera"]
    assert names(status="all", category="cruise") == ["Naviera"]


@pytest.mark.parametrize(
    "query", [{"category": "spa"}, {"status": "deleted"}, {"q": "a" * 101}, {"q": "a\x00b"}]
)
def test_invalid_filters_answer_422(auth_client, query):
    client = auth_client(permissions=VIEW)

    assert client.get("/api/suppliers", params=query).status_code == 422


def test_the_detail_answers_every_field(auth_client):
    client = auth_client(permissions=MANAGE)
    created = register(client)

    detail = client.get(f"/api/suppliers/{created['id']}").json()

    assert detail["categories"] == ["lodging", "tours"]
    assert detail["commission_rate"] == "10.00"
    assert (detail["agreement_valid_until"], detail["agreement_expired"]) == ("2027-06-30", False)
    assert (detail["contact_phone"], detail["contact_role"]) == ("+573001112233", "Reservas")
    assert (detail["deactivated_at"], detail["deactivated_by"]) == (None, None)
    assert set(detail["created_by"]) == {"id", "full_name"}
    assert detail["created_by"] == created["created_by"]
    assert detail["version"] == 1


@pytest.mark.parametrize(
    "valid_until, expired",
    [
        pytest.param("2026-10-30", False, id="last-day"),
        pytest.param("2026-10-29", True, id="day-after"),
    ],
)
def test_the_agreement_expires_the_day_after_with_the_bogota_date(
    auth_client, monkeypatch, valid_until, expired
):
    monkeypatch.setattr(models, "today", lambda: date(2026, 10, 30))
    client = auth_client(permissions=MANAGE)
    created = register(client, agreement_valid_until=valid_until)

    assert client.get(f"/api/suppliers/{created['id']}").json()["agreement_expired"] is expired


@pytest.mark.parametrize(
    "path, status",
    [("/api/suppliers/999999999", 404), ("/api/suppliers/0", 422), ("/api/suppliers/abc", 422)],
)
def test_an_unknown_or_impossible_id(auth_client, path, status):
    client = auth_client(permissions=MANAGE)
    version = {"expected_version": 1}

    assert client.get(path).status_code == status
    assert client.put(path, json=HOTEL | version).status_code == status
    assert client.post(f"{path}/deactivate", json=version).status_code == status
    assert client.post(f"{path}/activate", json=version).status_code == status


# --- Escritura -----------------------------------------------------------------------------


def test_registering_answers_201_with_the_detail(auth_client):
    client = auth_client(permissions=MANAGE)

    detail = register(client)

    assert detail["document_number"] == "8001972684"
    assert detail["is_active"] is True


def test_missing_data_answers_422_with_each_field(auth_client):
    client = auth_client(permissions=MANAGE)
    body = HOTEL | {"trade_name": "", "categories": [], "contact_phone": None}
    del body["contact_email"]

    response = client.post("/api/suppliers", json=body)

    assert (response.status_code, response.json()["code"]) == (422, "validation_error")
    assert response.json()["fields"] == {
        "trade_name": ["Este campo es obligatorio."],
        "categories": ["Elige al menos una clasificación."],
        "contact_phone": ["Indica un teléfono o un correo de contacto."],
        "contact_email": ["Indica un teléfono o un correo de contacto."],
    }


def test_a_repeated_document_answers_422_and_is_not_logged(auth_client, caplog):
    client = auth_client(permissions=MANAGE)
    register(client)

    with caplog.at_level(logging.DEBUG):
        response = client.post("/api/suppliers", json=HOTEL)

    assert response.status_code == 422
    assert response.json()["fields"] == {
        "document_number": ["Ya existe un proveedor con ese documento."]
    }
    assert "8001972684" not in caplog.text


def test_editing_answers_the_saved_detail(auth_client):
    client = auth_client(permissions=MANAGE)
    created = register(client)

    response = client.put(
        f"/api/suppliers/{created['id']}", json=editable(created, city="Santa Marta")
    )

    assert response.status_code == 200
    assert (response.json()["city"], response.json()["version"]) == ("Santa Marta", 2)


def test_editing_over_an_old_version_answers_409(auth_client):
    client = auth_client(permissions=MANAGE)
    created = register(client)
    client.put(f"/api/suppliers/{created['id']}", json=editable(created, city="Santa Marta"))

    response = client.put(f"/api/suppliers/{created['id']}", json=editable(created, city="Cali"))

    assert (response.status_code, response.json()["code"]) == (409, "stale_version")


@pytest.mark.parametrize(
    "extra", [{"is_active": False}, {"created_by_id": 1}, {"deactivated_at": None}]
)
def test_editing_rejects_what_is_not_editable(auth_client, extra):
    client = auth_client(permissions=MANAGE)
    created = register(client)

    response = client.put(f"/api/suppliers/{created['id']}", json=editable(created) | extra)

    assert response.status_code == 422


def test_deactivating_and_activating(auth_client):
    client = auth_client(permissions=MANAGE)
    created = register(client)
    path = f"/api/suppliers/{created['id']}"

    deactivated = client.post(f"{path}/deactivate", json={"expected_version": 1})
    activated = client.post(f"{path}/activate", json={"expected_version": 2})

    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert deactivated.json()["deactivated_by"] == deactivated.json()["created_by"]
    assert activated.status_code == 200
    assert (activated.json()["is_active"], activated.json()["deactivated_at"]) == (True, None)


def test_changing_the_status_over_an_old_version_answers_409(auth_client):
    client = auth_client(permissions=MANAGE)
    created = register(client)
    client.put(f"/api/suppliers/{created['id']}", json=editable(created, city="Santa Marta"))

    response = client.post(
        f"/api/suppliers/{created['id']}/deactivate", json={"expected_version": 1}
    )

    assert (response.status_code, response.json()["code"]) == (409, "stale_version")


def test_the_openapi_describes_the_supplier_endpoints(app):
    paths = app.openapi()["paths"]

    assert set(paths["/api/suppliers"]) == {"get", "post"}
    assert set(paths["/api/suppliers/{supplier_id}"]) == {"get", "put"}
    assert set(paths["/api/suppliers/{supplier_id}/deactivate"]) == {"post"}
    assert set(paths["/api/suppliers/{supplier_id}/activate"]) == {"post"}
    assert "Page_SupplierListItem_" in str(paths["/api/suppliers"]["get"])
