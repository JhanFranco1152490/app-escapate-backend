import logging
from datetime import date

import pytest

from app.core.security.csrf import CSRF_HEADER
from tests.factories import (
    ClientFactory,
    TravelerFactory,
    TravelRequestFactory,
    TravelRequestTravelerFactory,
    UserAccountFactory,
)

BOTH_VIEWS = ["travel_requests.view", "travelers.view"]
MANAGE = ["travel_requests.view", "travel_requests.manage", "travelers.view"]

READ_ENDPOINTS = [("get", "/api/travel-requests/1/travelers")]
WRITE_ENDPOINTS = [
    ("post", "/api/travel-requests/1/travelers"),
    ("delete", "/api/travel-requests/1/travelers/1"),
]


@pytest.fixture
def advisor(session, advisor_role):
    return UserAccountFactory(role=advisor_role, first_name="Laura", last_name="Rojas")


@pytest.fixture
def manager(auth_client, advisor):
    """Un asesor comercial con sesión: gestiona solicitudes y ve viajeros."""
    return auth_client(user=advisor)


def path(request, traveler=None) -> str:
    base = f"/api/travel-requests/{request.id}/travelers"
    return base if traveler is None else f"{base}/{traveler.id}"


def associate(api, request, *travelers):
    return api.post(path(request), json={"traveler_ids": [t.id for t in travelers]})


# --- Acceso --------------------------------------------------------------------------------


@pytest.mark.parametrize("method, url", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_a_session_every_endpoint_answers_401(csrf_client, method, url):
    assert csrf_client.request(method, url, json={}).status_code == 401


@pytest.mark.parametrize(
    "permissions",
    [
        pytest.param(["travel_requests.view", "travel_requests.manage"], id="no-travelers-view"),
        pytest.param(["travelers.view"], id="no-requests-view"),
    ],
)
@pytest.mark.parametrize("method, url", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_both_permissions_are_needed(auth_client, permissions, method, url):
    client = auth_client(permissions=permissions)

    response = client.request(method, url, json={})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, url", WRITE_ENDPOINTS)
def test_viewing_is_not_enough_to_change_the_travelers(auth_client, method, url):
    client = auth_client(permissions=BOTH_VIEWS)

    response = client.request(method, url, json={})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, url", WRITE_ENDPOINTS)
def test_changes_need_the_csrf_token(manager, method, url):
    del manager.headers[CSRF_HEADER]

    assert manager.request(method, url, json={}).status_code == 403


def test_operations_staff_see_the_travelers_but_do_not_change_them(auth_client, operations_role):
    link = TravelRequestTravelerFactory()
    viewer = auth_client(user=UserAccountFactory(role=operations_role))

    assert viewer.get(path(link.travel_request)).status_code == 200
    assert associate(viewer, link.travel_request, TravelerFactory()).status_code == 403
    assert viewer.delete(path(link.travel_request, link.traveler)).status_code == 403


# --- Asociar (HU-09 CA-01, CA-04) ----------------------------------------------------------


def test_associating_answers_every_traveler_of_the_request(manager, advisor):
    client = ClientFactory()
    request = TravelRequestFactory(client=client)
    titular = TravelerFactory(
        first_name="Marcela",
        last_name="Gómez Ortiz",
        birth_date=date(1988, 4, 2),
        reference_client=client,
        is_the_client=True,
    )
    minor = TravelerFactory(document_type="TI", birth_date=date(2012, 6, 9))

    response = associate(manager, request, titular, minor)

    assert response.status_code == 200
    body = {item["id"]: item for item in response.json()}
    assert set(body) == {titular.id, minor.id}
    assert body[titular.id]["full_name"] == "Marcela Gómez Ortiz"
    assert body[titular.id]["is_the_client"] is True
    assert body[titular.id]["is_minor"] is False
    assert body[titular.id]["added_by"] == {"id": advisor.id, "full_name": "Laura Rojas"}
    assert body[minor.id]["document_type"] == "TI"
    assert body[minor.id]["is_minor"] is True
    assert body[minor.id]["is_the_client"] is False


def test_the_list_does_not_bring_private_traveler_data(manager):
    link = TravelRequestTravelerFactory()

    item = manager.get(path(link.travel_request)).json()[0]

    assert not {"birth_date", "nationality", "notes"} & set(item)


def test_an_invalid_list_answers_422_on_its_field(manager):
    response = associate(manager, TravelRequestFactory())

    assert response.status_code == 422
    assert response.json()["fields"] == {"traveler_ids": ["Elige al menos un viajero."]}


def test_an_unknown_traveler_answers_422_without_logging_names(manager, caplog):
    request = TravelRequestFactory()
    known = TravelerFactory(first_name="Nombre", last_name="Reservado")

    with caplog.at_level(logging.DEBUG):
        response = manager.post(path(request), json={"traveler_ids": [known.id, 2**62]})

    assert response.status_code == 422
    assert response.json()["fields"] == {"traveler_ids": ["Uno de los viajeros no existe."]}
    assert "Reservado" not in caplog.text
    assert known.document_number not in caplog.text


def test_an_unknown_request_answers_404(manager):
    traveler = TravelerFactory()

    assert manager.get("/api/travel-requests/999999999/travelers").status_code == 404
    response = manager.post(
        "/api/travel-requests/999999999/travelers", json={"traveler_ids": [traveler.id]}
    )
    assert response.status_code == 404
    assert (
        manager.delete(f"/api/travel-requests/999999999/travelers/{traveler.id}").status_code
        == 404
    )


def test_a_closed_request_answers_409(manager):
    link = TravelRequestTravelerFactory(travel_request=TravelRequestFactory(closed=True))

    added = associate(manager, link.travel_request, TravelerFactory())
    removed = manager.delete(path(link.travel_request, link.traveler))

    for response in (added, removed):
        assert (response.status_code, response.json()["code"]) == (409, "travel_request_closed")


# --- Consultar y quitar (HU-09 CA-02, CA-03) -----------------------------------------------


def test_an_associated_traveler_appears_among_the_participants(manager):
    request, traveler = TravelRequestFactory(), TravelerFactory()
    associate(manager, request, traveler)

    response = manager.get(path(request))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [traveler.id]


def test_removing_answers_204_and_keeps_the_traveler(manager):
    link = TravelRequestTravelerFactory()

    response = manager.delete(path(link.travel_request, link.traveler))

    assert response.status_code == 204
    assert manager.get(path(link.travel_request)).json() == []
    assert manager.get(f"/api/travelers/{link.traveler_id}").status_code == 200


def test_removing_twice_answers_204_both_times(manager):
    link = TravelRequestTravelerFactory()

    first = manager.delete(path(link.travel_request, link.traveler))
    second = manager.delete(path(link.travel_request, link.traveler))

    assert (first.status_code, second.status_code) == (204, 204)
