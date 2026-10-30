import logging

import pytest

from app.core.security.csrf import CSRF_HEADER
from tests.factories import ClientFactory

VIEW = ["clients.view"]
MANAGE = ["clients.view", "clients.manage"]

PERSON = {
    "client_type": "person",
    "first_name": "Marcela",
    "last_name": "Gómez Ortiz",
    "document_type": "CC",
    "document_number": "1.020.304.050",
    "phone": "300 111 2233",
    "email": "marcela.gomez@example.com",
    "city": "Cúcuta",
    "contact_source": "instagram",
    "notes": "Prefiere diciembre.",
}

READ_ENDPOINTS = [("get", "/api/clients"), ("get", "/api/clients/1")]
WRITE_ENDPOINTS = [("post", "/api/clients"), ("put", "/api/clients/1")]


def editable(detail: dict, **changes) -> dict:
    """El cuerpo del PUT a partir de la ficha, como lo arma el formulario de edición."""
    fields = [*PERSON, "business_name", "birth_date", "contact_source_detail"]
    body = {field: detail[field] for field in fields}
    return body | {"expected_version": detail["version"]} | changes


# --- Acceso --------------------------------------------------------------------------------


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_a_session_every_endpoint_answers_401(csrf_client, method, path):
    assert csrf_client.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_the_permission_every_endpoint_answers_403(auth_client, method, path):
    client = auth_client(permissions=["travelers.view"])

    response = client.request(method, path, json={})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_viewing_is_not_enough_to_change_clients(auth_client, method, path):
    client = auth_client(permissions=VIEW)

    assert client.request(method, path, json={}).status_code == 403


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_changes_need_the_csrf_token(auth_client, method, path):
    client = auth_client(permissions=MANAGE)
    del client.headers[CSRF_HEADER]

    assert client.request(method, path, json={}).status_code == 403


# --- Lectura -------------------------------------------------------------------------------


def test_the_list_answers_a_page_without_notes(auth_client):
    client = auth_client(permissions=VIEW)
    ClientFactory(first_name="Marcela", last_name="Gómez Ortiz", notes="Dato reservado")

    response = client.get("/api/clients", params={"q": "marcela"})

    assert response.status_code == 200
    page = response.json()
    assert page["count"] == 1
    assert set(page["results"][0]) == {
        "id",
        "client_type",
        "display_name",
        "email",
        "phone",
        "document_type",
        "document_number",
        "city",
    }


def test_the_list_filters_by_client_type(auth_client):
    client = auth_client(permissions=VIEW)
    ClientFactory()
    company = ClientFactory(company=True)

    response = client.get("/api/clients", params={"client_type": "company"})

    assert [item["id"] for item in response.json()["results"]] == [company.id]


@pytest.mark.parametrize("query", [{"client_type": "family"}, {"q": "a" * 101}])
def test_invalid_filters_answer_422(auth_client, query):
    client = auth_client(permissions=VIEW)

    assert client.get("/api/clients", params=query).status_code == 422


def test_the_detail_answers_every_field(auth_client):
    client = auth_client(permissions=VIEW)
    registered = ClientFactory(notes="Prefiere diciembre.")

    response = client.get(f"/api/clients/{registered.id}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["notes"] == "Prefiere diciembre."
    assert detail["created_by"] == {
        "id": registered.created_by_id,
        "full_name": registered.created_by.full_name,
    }
    assert detail["version"] == 1


@pytest.mark.parametrize(
    "path, status",
    [("/api/clients/999999999", 404), ("/api/clients/0", 422), ("/api/clients/abc", 422)],
)
def test_an_unknown_or_impossible_id(auth_client, path, status):
    client = auth_client(permissions=MANAGE)

    assert client.get(path).status_code == status
    assert client.put(path, json=PERSON | {"expected_version": 1}).status_code == status


# --- Escritura -----------------------------------------------------------------------------


def test_registering_answers_201_with_the_detail(auth_client):
    client = auth_client(permissions=MANAGE)

    response = client.post("/api/clients", json=PERSON | {"data_consent": True})

    assert response.status_code == 201
    detail = response.json()
    assert (detail["document_number"], detail["phone"]) == ("1020304050", "+573001112233")
    assert detail["data_consent_by"] == detail["created_by"]


def test_missing_data_answers_422_with_each_field(auth_client):
    client = auth_client(permissions=MANAGE)

    response = client.post(
        "/api/clients", json=PERSON | {"first_name": "", "phone": "123", "data_consent": False}
    )

    assert (response.status_code, response.json()["code"]) == (422, "validation_error")
    assert set(response.json()["fields"]) == {"first_name", "phone", "data_consent"}


def test_a_repeated_document_answers_422_and_is_not_logged(auth_client, caplog):
    client = auth_client(permissions=MANAGE)
    client.post("/api/clients", json=PERSON | {"data_consent": True})

    with caplog.at_level(logging.DEBUG):
        response = client.post("/api/clients", json=PERSON | {"data_consent": True})

    assert response.status_code == 422
    assert response.json()["fields"] == {
        "document_number": ["Ya existe un cliente con ese documento."]
    }
    assert "1020304050" not in caplog.text


def test_editing_answers_the_saved_detail(auth_client):
    client = auth_client(permissions=MANAGE)
    created = client.post("/api/clients", json=PERSON | {"data_consent": True}).json()

    response = client.put(f"/api/clients/{created['id']}", json=editable(created, city="Bogotá"))

    assert response.status_code == 200
    assert (response.json()["city"], response.json()["version"]) == ("Bogotá", 2)


def test_editing_over_an_old_version_answers_409(auth_client):
    client = auth_client(permissions=MANAGE)
    created = client.post("/api/clients", json=PERSON | {"data_consent": True}).json()
    client.put(f"/api/clients/{created['id']}", json=editable(created, city="Bogotá"))

    response = client.put(f"/api/clients/{created['id']}", json=editable(created, city="Cali"))

    assert (response.status_code, response.json()["code"]) == (409, "stale_version")


@pytest.mark.parametrize("extra", [{"data_consent": True}, {"created_by_id": 1}, {"version": 3}])
def test_editing_rejects_what_is_not_editable(auth_client, extra):
    client = auth_client(permissions=MANAGE)
    created = client.post("/api/clients", json=PERSON | {"data_consent": True}).json()

    response = client.put(f"/api/clients/{created['id']}", json=editable(created) | extra)

    assert response.status_code == 422


def test_changing_the_client_type_answers_422(auth_client):
    client = auth_client(permissions=MANAGE)
    created = client.post("/api/clients", json=PERSON | {"data_consent": True}).json()
    as_company = editable(
        created,
        client_type="company",
        first_name=None,
        last_name=None,
        business_name="Gómez SAS",
        document_type=None,
        document_number=None,
    )

    response = client.put(f"/api/clients/{created['id']}", json=as_company)

    assert response.json()["fields"] == {
        "client_type": ["El tipo de cliente no se puede cambiar."]
    }


def test_the_openapi_describes_the_client_endpoints(app):
    paths = app.openapi()["paths"]

    assert set(paths["/api/clients"]) == {"get", "post"}
    assert set(paths["/api/clients/{client_id}"]) == {"get", "put"}
    assert "Page_ClientListItem_" in str(paths["/api/clients"]["get"])
