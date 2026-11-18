import logging
from datetime import timedelta

import pytest

from app.common.dates import today
from app.core.security.csrf import CSRF_HEADER
from tests.factories import ClientFactory, TravelRequestFactory, UserAccountFactory

VIEW = ["travel_requests.view"]

READ_ENDPOINTS = [
    ("get", "/api/travel-requests"),
    ("get", "/api/travel-requests/summary"),
    ("get", "/api/travel-requests/advisors"),
    ("get", "/api/travel-requests/1"),
]
WRITE_ENDPOINTS = [
    ("post", "/api/travel-requests"),
    ("put", "/api/travel-requests/1"),
    ("post", "/api/travel-requests/1/close"),
    ("post", "/api/travel-requests/1/reopen"),
]


@pytest.fixture
def advisor(session, advisor_role):
    return UserAccountFactory(role=advisor_role, first_name="Laura", last_name="Rojas")


@pytest.fixture
def manager(auth_client, advisor):
    """Un asesor comercial con sesión: puede gestionar solicitudes y ser responsable."""
    return auth_client(user=advisor)


def in_days(days: int) -> str:
    return (today() + timedelta(days=days)).isoformat()


def new_request(client, advisor, **changes) -> dict:
    return {
        "client_id": client.id,
        "destination": "San Andrés",
        "origin": "Cúcuta",
        "date_mode": "exact",
        "departure_date": in_days(35),
        "return_date": in_days(41),
        "adults": 2,
        "minors": 1,
        "budget_min": 6_000_000,
        "budget_max": 8_000_000,
        "trip_types": ["family", "leisure"],
        "accommodation_category": "four_star",
        "assigned_to_id": advisor.id,
        "notes": "Prefieren habitación conectada.\nEvitar vuelos con escala nocturna.",
        **changes,
    }


def register(api, client, advisor, **changes) -> dict:
    response = api.post("/api/travel-requests", json=new_request(client, advisor, **changes))
    assert response.status_code == 201, response.json()
    return response.json()


def editable(detail: dict, **changes) -> dict:
    """El cuerpo del PUT a partir de la ficha, como lo arma el formulario de edición."""
    fields = [
        "destination",
        "origin",
        "date_mode",
        "departure_date",
        "return_date",
        "window_start",
        "window_end",
        "approx_nights",
        "adults",
        "minors",
        "budget_min",
        "budget_max",
        "trip_types",
        "accommodation_category",
        "notes",
    ]
    body = {field: detail[field] for field in fields}
    body |= {
        "client_id": detail["client"]["id"],
        "assigned_to_id": detail["assigned_to"]["id"],
        "expected_version": detail["version"],
    }
    return body | changes


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
def test_viewing_is_not_enough_to_change_requests(auth_client, method, path):
    client = auth_client(permissions=VIEW)

    response = client.request(method, path, json={})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_changes_need_the_csrf_token(manager, method, path):
    del manager.headers[CSRF_HEADER]

    assert manager.request(method, path, json={}).status_code == 403


# --- Registrar (HU-10) ---------------------------------------------------------------------


def test_registering_answers_the_saved_detail(manager, advisor):
    client = ClientFactory(first_name="Marcela", last_name="Gómez Ortiz")

    created = register(manager, client, advisor)

    assert created["code"] == f"SOL-{created['id']:04d}"
    assert created["status"] == "new"
    assert created["client"] == {"id": client.id, "display_name": "Marcela Gómez Ortiz"}
    assert created["assigned_to"] == {
        "id": advisor.id,
        "full_name": "Laura Rojas",
        "is_active": True,
    }
    assert created["created_by"]["id"] == advisor.id
    assert created["trip_types"] == ["leisure", "family"]
    assert (
        created["notes"] == "Prefieren habitación conectada.\nEvitar vuelos con escala nocturna."
    )
    assert created["waiting_days"] == 0
    assert created["version"] == 1


def test_registering_a_flexible_period(manager, advisor):
    created = register(
        manager,
        ClientFactory(),
        advisor,
        date_mode="flexible",
        departure_date=None,
        return_date=None,
        window_start=in_days(30),
        window_end=in_days(60),
        approx_nights=5,
    )

    assert (created["window_start"], created["approx_nights"]) == (in_days(30), 5)
    assert created["departure_date"] is None


def test_missing_data_is_reported_on_each_field(manager):
    response = manager.post("/api/travel-requests", json={"date_mode": "exact", "destination": ""})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert set(response.json()["fields"]) == {
        "client_id",
        "destination",
        "departure_date",
        "adults",
        "minors",
        "assigned_to_id",
    }


def test_a_trip_in_the_past_answers_422_without_logging_the_request(manager, advisor, caplog):
    with caplog.at_level(logging.DEBUG):
        response = manager.post(
            "/api/travel-requests",
            json=new_request(
                ClientFactory(),
                advisor,
                destination="Destino reservado",
                departure_date=in_days(-1),
                return_date=None,
            ),
        )

    assert response.status_code == 422
    assert response.json()["fields"] == {"departure_date": ["La fecha ya pasó."]}
    assert "Destino reservado" not in caplog.text
    assert "habitación conectada" not in caplog.text


def test_an_advisor_who_cannot_manage_requests_is_rejected(manager, operations_role):
    viewer = UserAccountFactory(role=operations_role)

    response = manager.post("/api/travel-requests", json=new_request(ClientFactory(), viewer))

    assert response.status_code == 422
    assert set(response.json()["fields"]) == {"assigned_to_id"}


def test_two_equal_requests_of_one_client_are_two_processes(manager, advisor):
    client = ClientFactory()

    first = register(manager, client, advisor)
    second = register(manager, client, advisor)

    assert first["id"] != second["id"]


# --- Consultar (HU-10 CA-04, HU-11) --------------------------------------------------------


def test_the_detail_shows_what_was_registered(manager, advisor):
    created = register(manager, ClientFactory(), advisor)

    response = manager.get(f"/api/travel-requests/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_an_unknown_request_answers_404(manager):
    response = manager.get("/api/travel-requests/999999999")

    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_the_list_answers_a_page_without_notes_budget_or_preferences(manager, advisor):
    register(manager, ClientFactory(), advisor)

    page = manager.get("/api/travel-requests").json()

    assert page["count"] == 1
    assert set(page["results"][0]) == {
        "id",
        "code",
        "client",
        "destination",
        "date_mode",
        "departure_date",
        "return_date",
        "window_start",
        "window_end",
        "approx_nights",
        "adults",
        "minors",
        "status",
        "assigned_to",
        "created_at",
        "updated_at",
        "waiting_days",
    }


@pytest.mark.parametrize(
    "query",
    [{"status": "won"}, {"sort": "random"}, {"assigned_to": "0"}, {"q": "a" * 101}],
)
def test_invalid_filters_answer_422(manager, query):
    assert manager.get("/api/travel-requests", params=query).status_code == 422


def test_filters_on_records_that_do_not_exist_answer_an_empty_page(manager, advisor):
    register(manager, ClientFactory(), advisor)

    for params in ({"assigned_to": 999_999_999}, {"client_id": 999_999_999}):
        response = manager.get("/api/travel-requests", params=params)
        assert (response.status_code, response.json()["count"]) == (200, 0)


# --- Pendientes de cotización (HU-13) ------------------------------------------------------


def test_pending_requests_are_listed_oldest_first_without_the_quoted_or_closed(manager):
    now = TravelRequestFactory()
    quoting = TravelRequestFactory(status="quoting")
    quoted = TravelRequestFactory(status="quoted")
    closed = TravelRequestFactory(closed=True)
    oldest = TravelRequestFactory()
    oldest.created_at = now.created_at - timedelta(days=6)

    page = manager.get(
        "/api/travel-requests", params={"status": "pending", "sort": "oldest"}
    ).json()

    ids = [item["id"] for item in page["results"]]
    assert ids[0] == oldest.id
    assert set(ids) == {now.id, quoting.id, oldest.id}
    assert not {quoted.id, closed.id} & set(ids)
    assert page["results"][0]["waiting_days"] == 6


def test_without_pending_requests_the_page_is_empty(manager):
    TravelRequestFactory(status="quoted")

    page = manager.get("/api/travel-requests", params={"status": "pending"}).json()

    assert (page["count"], page["results"]) == (0, [])


def test_the_summary_counts_by_status(manager, advisor):
    TravelRequestFactory(assigned_to=advisor)
    TravelRequestFactory(assigned_to=advisor, status="quoting")
    TravelRequestFactory(closed=True)

    mine = manager.get("/api/travel-requests/summary", params={"assigned_to": advisor.id})
    everyone = manager.get("/api/travel-requests/summary")

    assert mine.status_code == 200
    assert mine.json() == {
        "by_status": {"new": 1, "quoting": 1, "quoted": 0, "closed": 0},
        "total": 2,
        "pending": 2,
        "pending_over_3_days": 0,
    }
    assert everyone.json()["by_status"]["closed"] == 1


def test_the_advisors_are_the_people_who_can_manage_requests(manager, advisor, operations_role):
    UserAccountFactory(role=operations_role)

    response = manager.get("/api/travel-requests/advisors")

    assert response.status_code == 200
    assert {"id": advisor.id, "full_name": "Laura Rojas"} in response.json()
    assert all(set(option) == {"id", "full_name"} for option in response.json())


# --- Editar (HU-11) ------------------------------------------------------------------------


def test_editing_answers_the_saved_detail(manager, advisor):
    created = register(manager, ClientFactory(), advisor)

    response = manager.put(
        f"/api/travel-requests/{created['id']}",
        json=editable(created, destination="Cartagena", minors=2),
    )

    assert response.status_code == 200
    assert (response.json()["destination"], response.json()["minors"]) == ("Cartagena", 2)
    assert response.json()["version"] == 2


def test_editing_without_a_required_field_answers_422_and_saves_nothing(manager, advisor):
    created = register(manager, ClientFactory(), advisor)

    response = manager.put(
        f"/api/travel-requests/{created['id']}", json=editable(created, departure_date=None)
    )
    unchanged = manager.get(f"/api/travel-requests/{created['id']}").json()

    assert response.status_code == 422
    assert response.json()["fields"] == {"departure_date": ["Indica la fecha de salida."]}
    assert unchanged["version"] == 1


def test_editing_another_client_answers_422(manager, advisor):
    created = register(manager, ClientFactory(), advisor)

    response = manager.put(
        f"/api/travel-requests/{created['id']}",
        json=editable(created, client_id=ClientFactory().id),
    )

    assert response.status_code == 422
    assert set(response.json()["fields"]) == {"client_id"}


def test_editing_over_an_old_version_answers_409(manager, advisor):
    created = register(manager, ClientFactory(), advisor)
    path = f"/api/travel-requests/{created['id']}"
    manager.put(path, json=editable(created, destination="Cartagena"))

    response = manager.put(path, json=editable(created, destination="Santa Marta"))

    assert (response.status_code, response.json()["code"]) == (409, "stale_version")


# --- Cerrar y reabrir ----------------------------------------------------------------------


def test_closing_and_reopening(manager, advisor):
    created = register(manager, ClientFactory(), advisor)
    path = f"/api/travel-requests/{created['id']}"

    closed = manager.post(
        f"{path}/close",
        json={"reason": "other", "note": "Aplazó el viaje.", "expected_version": 1},
    )
    reopened = manager.post(f"{path}/reopen", json={"expected_version": 2})

    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["closed_by"]["id"] == advisor.id
    assert closed.json()["close_note"] == "Aplazó el viaje."
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "new"
    assert reopened.json()["closed_by"] is None


def test_closing_with_other_needs_a_note(manager, advisor):
    created = register(manager, ClientFactory(), advisor)

    response = manager.post(
        f"/api/travel-requests/{created['id']}/close",
        json={"reason": "other", "expected_version": 1},
    )

    assert response.status_code == 422
    assert response.json()["fields"] == {"note": ["Cuéntanos el motivo."]}


def test_a_closed_request_cannot_be_edited_or_closed_again(manager, advisor):
    created = register(manager, ClientFactory(), advisor)
    path = f"/api/travel-requests/{created['id']}"
    manager.post(f"{path}/close", json={"reason": "duplicate", "expected_version": 1})

    edit = manager.put(path, json=editable(created, expected_version=2))
    close = manager.post(f"{path}/close", json={"reason": "duplicate", "expected_version": 2})

    for response in (edit, close):
        assert (response.status_code, response.json()["code"]) == (409, "travel_request_closed")
        assert response.json()["detail"] == (
            "La solicitud está cerrada. Reábrela para modificarla."
        )


def test_reopening_an_open_request_answers_409(manager, advisor):
    created = register(manager, ClientFactory(), advisor)

    response = manager.post(
        f"/api/travel-requests/{created['id']}/reopen", json={"expected_version": 1}
    )

    assert (response.status_code, response.json()["code"]) == (409, "travel_request_not_closed")


def test_closing_an_unknown_request_answers_404(manager):
    response = manager.post(
        "/api/travel-requests/999999999/close",
        json={"reason": "duplicate", "expected_version": 1},
    )

    assert response.status_code == 404
